# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""HDF5-based file IO for PyMVPA objects.

Based on the `h5py` package, this module provides two functions (`obj2hdf()`
and `hdf2obj()`, as well as the convenience functions `h5save()` and
`h5load()`) to store (in principle) arbitrary Python objects into HDF5 groups,
and using HDF5 as input, convert them back into Python object instances.

Similar to `pickle` a Python object is disassembled into its pieces, but instead
of serializing it into a byte-stream it is stored in chunks which type can be
natively stored in HDF5. That means basically everything that can be stored in
a NumPy array.

If an object is not readily storable, its `__reduce__()` method is called to
disassemble it into basic pieces.  The default implementation of
`object.__reduce__()` is typically sufficient. Hence, for any new-style Python
class there is, in general, no need to implement `__reduce__()`. However, custom
implementations might allow for leaner HDF5 representations and leaner files.
Basic types, such as `list`, and `dict`, which `__reduce__()` method does not do
help with disassembling are also handled.

.. warning::

  Although, in principle, storage and reconstruction of arbitrary object types
  is possible, it might not be implemented yet. The current focus lies on
  storage of PyMVPA datasets and their attributes (e.g. Mappers).  Especially,
  objects with recursive references will cause problems with the current
  implementation.
"""

__docformat__ = 'restructuredtext'

import numpy as N
import h5py
from mvpa.base.types import asobjarray


#
# TODO: check for recursions!!!
#
def hdf2obj(hdf):
    """Convert an HDF5 group definition into an object instance.

    Obviously, this function assumes the conventions implemented in the
    `obj2hdf()` function. Those conventions will eventually be documented in
    the module docstring, whenever they are sufficiently stable.

    Parameters
    ----------
    hdf : HDF5 group instance
      HDF5 group instance. this could also be an HDF5 file instance.

    Notes
    -----
    Although, this function uses a way to reconstruct object instances that is
    similar to unpickling, it should be *relatively* safe to open HDF files
    from untrusted sources. Only basic datatypes are stored in HDF files, and
    there is no foreign code that is executed during reconstructing. For that
    reason, any type that shall be reconstructed needs to be importable
    (importing is done be fully-qualified module names).

    Returns
    -------
    object instance
    """
    # already at the level of real data
    if isinstance(hdf, h5py.Dataset):
        if not len(hdf.shape):
            # extract the scalar from the 0D array
            return hdf[()]
        else:
            # read array-dataset into an array
            value = N.empty(hdf.shape, hdf.dtype)
            hdf.read_direct(value)
            return value
    else:
        # check if we have a class instance definition here
        if not ('class' in hdf.attrs or 'recon' in hdf.attrs):
            raise RuntimeError("Found hdf group without class instance "
                    "information (group: %s). This is a conceptual bug in the "
                    "parser or the hdf writer. Please report." % hdf.name)

        if 'recon' in hdf.attrs:
            # we found something that has some special idea about how it wants
            # to be reconstructed
            # look for arguments for that reconstructor
            recon = hdf.attrs['recon']
            mod = hdf.attrs['module']
            if mod == '__builtin__':
                raise NotImplementedError(
                        "Built-in reconstructors are not supported (yet). "
                        "Got: '%s'." % recon)

            # turn names into definitions
            mod = __import__(mod, fromlist=[recon])
            recon = mod.__dict__[recon]

            if 'rcargs' in hdf:
                recon_args = _hdf_tupleitems_to_obj(hdf['rcargs'])
            else:
                recon_args = ()

            # reconstruct
            obj = recon(*recon_args)

            # TODO Handle potentially avialable state settings
            return obj

        cls = hdf.attrs['class']
        mod = hdf.attrs['module']
        if not mod == '__builtin__':
            # some custom class is desired
            # import the module and the class
            mod = __import__(mod, fromlist=[cls])
            # get the class definition from the module dict
            cls = mod.__dict__[cls]

            # create the object
            if issubclass(cls, dict):
                # use specialized __new__ if necessary or beneficial
                obj = dict.__new__(cls)
            else:
                obj = object.__new__(cls)

            if 'state' in hdf:
                # insert the state of the object
                obj.__dict__.update(
                        _hdf_dictitems_to_obj(hdf['state']))

            # do we process a container?
            if 'items' in hdf:
                if issubclass(cls, dict):
                    # charge a dict itself
                    obj.update(_hdf_dictitems_to_obj(hdf['items']))
                else:
                    raise NotImplementedError(
                            "Unhandled conatiner typ (got: '%s')." % cls)

            return obj

        else:
            # built in type (there should be only 'list', 'dict' and 'None'
            # that would not be in a Dataset
            if cls == 'NoneType':
                return None
            elif cls == 'tuple':
                return _hdf_tupleitems_to_obj(hdf['items'])
            elif cls == 'list':
                l = _hdf_listitems_to_obj(hdf['items'])
                if 'is_objarray' in hdf.attrs:
                    # need to handle special case of arrays of objects
                    return asobjarray(l)
                else:
                    return l
            elif cls == 'dict':
                return _hdf_dictitems_to_obj(hdf['items'])
            else:
                raise RuntimeError("Found hdf group with a builtin type "
                        "that is not handled by the parser (group: %s). This "
                        "is a conceptual bug in the parser. Please report."
                        % hdf.name)


def _hdf_dictitems_to_obj(hdf, skip=None):
    if skip is None:
        skip = []
    return dict([(item, hdf2obj(hdf[item]))
                    for item in hdf
                        if not item in skip])


def _hdf_listitems_to_obj(hdf):
    return [hdf2obj(hdf[str(i)]) for i in xrange(len(hdf))]


def _hdf_tupleitems_to_obj(hdf):
    return tuple(_hdf_listitems_to_obj(hdf))

#
# TODO: check for recursions!!!
#
def obj2hdf(hdf, obj, name=None, **kwargs):
    """Store an object instance in an HDF5 group.

    A given object instance is (recursively) disassembled into pieces that are
    storable in HDF5. In general, any pickable object should be storable, but
    since the parser is not complete, it might not be possible (yet).

    .. warning::

      Currently, the parser does not track recursions. If an object contains
      recursive references all bets are off. Here be dragons...

    Parameters
    ----------
    hdf : HDF5 group instance
      HDF5 group instance. this could also be an HDF5 file instance.
    obj : object instance
      Object instance that shall be stored.
    name : str or None
      Name of the object. In case of a complex object that cannot be stored
      natively without disassembling them, this is going to be a new group,
      Otherwise the name of the dataset. If None, no new group is created.
    **kwargs
      All additional arguments will be passed to `h5py.Group.create_dataset()`
    """
    # if it is something that can go directly into HDF5, put it there
    # right away
    if N.isscalar(obj) \
       or (isinstance(obj, N.ndarray) and not obj.dtype == N.object):
        hdf.create_dataset(name, None, None, obj, **kwargs)
        return

    if not name is None:
        # complex objects
        grp = hdf.create_group(name)
    else:
        grp = hdf

    # special case of array of type object -- we turn them into lists and
    # process as usual, but set a flag to trigger appropriate reconstruction
    if isinstance(obj, N.ndarray) and obj.dtype == N.object:
        obj = list(obj)
        grp.attrs.create('is_objarray', True)

    # try disassembling the object
    try:
        pieces = obj.__reduce__()
    except TypeError:
        # probably a container
        pieces = None

    # common container handling, either __reduce__ was not possible
    # or it was the default implementation
    if pieces is None or pieces[0].__name__ == '_reconstructor':
        # store class info (fully-qualified)
        grp.attrs.create('class', obj.__class__.__name__)
        grp.attrs.create('module', obj.__class__.__module__)
        if isinstance(obj, list) or isinstance(obj, tuple):
            items = grp.create_group('items')
            for i, item in enumerate(obj):
                obj2hdf(items, item, str(i), **kwargs)
        elif isinstance(obj, dict):
            items = grp.create_group('items')
            for key in obj:
                obj2hdf(items, obj[key], key, **kwargs)
        # pull all remaining data from the default __reduce__
        if not pieces is None and len(pieces) > 2:
            stategrp = grp.create_group('state')
            # there is something in the state
            state = pieces[2]
            # loop over all attributes and store them
            for attr in state:
                obj2hdf(stategrp, state[attr], attr, **kwargs)
        # for the default __reduce__ there is nothin else to do
        return
    else:
        # XXX handle custom reduce
        grp.attrs.create('recon', pieces[0].__name__)
        grp.attrs.create('module', pieces[0].__module__)
        args = grp.create_group('rcargs')
        for i, arg in enumerate(pieces[1]):
            obj2hdf(args, arg, str(i), **kwargs)
        return


def h5save(filename, data, name=None, mode='w', **kwargs):
    """Stores arbitray data in an HDF5 file.

    This is a convenience wrapper around `obj2hdf()`. Please see its
    documentation for more details -- especially the warnings!!

    Parameters
    ----------
    filename : str
      Name of the file the data shall be stored in.
    data : arbitrary
      Instance of an object that shall be stored in the file.
    name : str or None
      Name of the object. In case of a complex object that cannot be stored
      natively without disassembling them, this is going to be a new group,
      otherwise the name of the dataset. If None, no new group is created.
    mode : {'r', 'r+', 'w', 'w-', 'a'}
      IO mode of the HDF5 file. See `h5py.File` documentation for more
      information.
    **kwargs
      All additional arguments will be passed to `h5py.Group.create_dataset`.
      This could, for example, be `compression='gzip'`.
    """
    hdf = h5py.File(filename, mode)
    try:
        obj2hdf(hdf, data, name, **kwargs)
    finally:
        hdf.close()


def h5load(filename, name=None):
    """Loads the content of an HDF5 file that has been stored by `h5save()`.

    This is a convenience wrapper around `hdf2obj()`. Please see its
    documentation for more details.

    Parameters
    ----------
    filename : str
      Name of the file to open and load its content.
    name : str
      Name of a specific object to load from the file.

    Returns
    -------
    instance
      An object of whatever has been stored in the file.
    """
    hdf = h5py.File(filename, 'r')
    try:
        if not name is None:
            if not name in hdf:
                raise ValueError("No object of name '%s' in file '%s'."
                                 % (name, filename))
            obj = hdf2obj(hdf[name])
        else:
            obj = hdf2obj(hdf)
    finally:
        hdf.close()
    return obj