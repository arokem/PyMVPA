# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

__docformat__ = 'restructuredtext'

import numpy as N

from mvpa.base.dochelpers import enhanced_doc_string
from mvpa.mappers.base import Mapper, accepts_dataset_as_samples


if __debug__:
    from mvpa.base import debug


class ProjectionMapper(Mapper):
    """Linear mapping between multidimensional spaces.

    This class cannot be used directly. Sub-classes have to implement
    the `_train()` method, which has to compute the projection matrix
    `_proj` and optionally offset vectors `_offset_in` and
    `_offset_out` (if initialized with demean=True, which is default)
    given a dataset (see `_train()` docstring for more information).

    Once the projection matrix is available, this class provides
    functionality to perform forward and backwards linear mapping of
    data, the latter by default using pseudo-inverse (but could be
    altered in subclasses, like hermitian (conjugate) transpose in
    case of SVD).  Additionally, `ProjectionMapper` supports optional
    selection of arbitrary component (i.e. columns of the projection
    matrix) of the projection.

    Forward and back-projection matrices (a.k.a. *projection* and
    *reconstruction*) are available via the `proj` and `recon`
    properties.
    """

    _DEV__doc__ = """Think about renaming `demean`, may be `translation`?"""

    def __init__(self, selector=None, demean=True):
        """Initialize the ProjectionMapper

        Parameters
        ----------
        selector : None or list
          Which components (i.e. columns of the projection matrix)
          should be used for mapping. If `selector` is `None` all
          components are used. If a list is provided, all list
          elements are treated as component ids and the respective
          components are selected (all others are discarded).
        demean : bool
          Either data should be demeaned while computing
          projections and applied back while doing reverse()
        """
        Mapper.__init__(self)

        self._selector = selector
        self._proj = None
        """Forward projection matrix."""
        self._recon = None
        """Reverse projection (reconstruction) matrix."""
        self._demean = demean
        """Flag whether to demean the to be projected data, prior to projection.
        """
        self._offset_in = None
        """Offset (most often just mean) in the input space"""
        self._offset_out = None
        """Offset (most often just mean) in the output space"""

    __doc__ = enhanced_doc_string('ProjectionMapper', locals(), Mapper)


    @accepts_dataset_as_samples
    def _pretrain(self, samples):
        """Determine the projection matrix.

        Parameters
        ----------
        dataset : Dataset
          Dataset to operate on
        """
        if self._demean:
            self._offset_in = samples.mean(axis=0)


    def _posttrain(self, dataset):
        # perform component selection
        if self._selector is not None:
            self.selectOut(self._selector)


    ##REF: Name was automagically refactored
    def _demean_data(self, data):
        """Helper which optionally demeans
        """
        if self._demean:
            # demean the training data
            data = data - self._offset_in

            if __debug__ and "MAP_" in debug.active:
                debug("MAP_",
                      "%s: Mean of data in input space %s was subtracted" %
                      (self.__class__.__name__, self._offset_in))
        return data


    def _forward_data(self, data):
        if self._proj is None:
            raise RuntimeError, "Mapper needs to be train before used."

        # local binding
        demean = self._demean

        d = N.asmatrix(data)

        # Remove input offset if present
        if demean and self._offset_in is not None:
            d = d - self._offset_in

        # Do forward projection
        res = (d * self._proj).A

        # Add output offset if present
        if demean and self._offset_out is not None:
            res += self._offset_out

        return res


    def _reverse_data(self, data):
        if self._proj is None:
            raise RuntimeError, "Mapper needs to be trained before used."
        d = N.asmatrix(data)
        # Remove offset if present in output space
        if self._demean and self._offset_out is not None:
            d = d - self._offset_out

        # Do reverse projection
        res = (d * self.recon).A

        # Add offset in input space
        if self._demean and self._offset_in is not None:
            res += self._offset_in

        return res


    ##REF: Name was automagically refactored
    def _compute_recon(self):
        """Given that a projection is present -- compute reconstruction matrix.
        By default -- pseudoinverse of projection matrix.  Might be overridden
        in derived classes for efficiency.
        """
        return N.linalg.pinv(self._proj)


    ##REF: Name was automagically refactored
    def _get_recon(self):
        """Compute (if necessary) and return reconstruction matrix
        """
        # (re)build reconstruction matrix
        recon = self._recon
        if recon is None:
            self._recon = recon = self._compute_recon()
        return recon


    proj  = property(fget=lambda self: self._proj, doc="Projection matrix")
    recon = property(fget=_get_recon, doc="Backprojection matrix")