#emacs: -*- mode: python-mode; py-indent-offset: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   Copyright (c) 2008 Emanuele Olivetti <emanuele@relativita.com>
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Kernels for Gaussian Process Regression and Classification."""

__docformat__ = 'restructuredtext'


import numpy as N

from scipy import weave
from scipy.weave import converters

if __debug__:
    import time
    from mvpa.misc import debug


class Kernel(object):
    """Kernel function base class.

    """

    def __init__(self):
        self.euclidean_distance_matrix = None

    def __repr__(self):
        return "Kernel()"

    def euclidean_distance(self, data1, data2=None, symmetric=False,
                           weight=None):
        """Compute weighted euclidean distance matrix between two datasets.


        :Parameters:
          data1 : numpy.ndarray
              first dataset
          data2 : numpy.ndarray
              second dataset. If None set symmetric to True.
              (Defaults to None)
          symmetric : bool
              compute the euclidean distance between the first dataset versus
              itself (True) or the second one (False). Note that
              (Defaults to False)
          weight : numpy.ndarray
              vector of weights, each one associated to each dimension of the
              dataset (Defaults to None)
        """

        if data2 is None:
            data2 = data1
            symmetric = True

        size1 = data1.shape[0]
        size2 = data2.shape[0]
        F = data1.shape[1]
        if weight is None:
            weight = N.ones(F,'d') # unitary weight

        euclidean_distance_matrix = N.zeros((data1.shape[0], data2.shape[0]),
                                            'd')
        code = None
        if not symmetric:
            code = """
            int i,j,t;
            double tmp,distance;
            for (i=0;i<size1;i++) {
                for (j=0;j<size2;j++) {
                    tmp = 0.0;
                    for(t=0;t<F;t++) {
                        distance = data1(i,t)-data2(j,t);
                        tmp = tmp+distance*distance*weight(t);
                        }
                    euclidean_distance_matrix(i,j) = tmp;
                    }
                }
            return_val = 0;
            """
        else:
            code = """
            int i,j,t;
            double tmp,distance;
            for (i=0;i<size1-1;i++) {
                for (j=i;j<size2;j++) {
                    tmp = 0.0;
                    for(t=0;t<F;t++) {
                        distance = data1(i,t)-data2(j,t);
                        tmp = tmp+distance*distance*weight(t);
                        }
                    euclidean_distance_matrix(i,j) = tmp;
                    }
                }
            return_val = 0;
            """

        if __debug__:
            t = time.time()
        retval = weave.inline(code,
                              ['data1','size1','data2','size2','F',
                               'euclidean_distance_matrix','weight'],
                              type_converters=converters.blitz,
                              compiler = 'gcc')
        if symmetric:
            # copy upper part to lower part
            euclidean_distance_matrix = euclidean_distance_matrix + \
                                        N.triu(euclidean_distance_matrix).T

        if __debug__:
            # XXX not need to report time took to complete -- could be
            # assessed from using MVPA_DEBUG_METRICS=reltime environment
            # variable
            debug('KERNEL', "Distance matrix computed in %s sec." % (time.time() - t))
        self.euclidean_distance_matrix = euclidean_distance_matrix
        return self.euclidean_distance_matrix


class KernelSquaredExponential(Kernel):
    """The Squared Exponential kernel function class.

    """
    def __init__(self, length_scale=0.01, **kwargs):
        """Initialize the Squared Exponential class.

        :Parameters:
          length_scale : float
            the characteristic lengthscale of the phenomenon under investigation.
            (Defaults to 0.01)
        """
        # init base class first
        Kernel.__init__(self, **kwargs)

        self.length_scale = length_scale
        self.kernel_matrix = None


    def __repr__(self):
        return "%s=%f)" % (self.__class__.__name__, self.length_scale)

    def compute(self, data1, data2=None):
        """Compute kernel matrix.

        :Parameters:
          data1 : numpy.ndarray
            data
          data2 : numpy.ndarray
            data
        """
        self.kernel_matrix = N.exp(-self.euclidean_distance(data1, data2) \
                                   /(2.0*self.length_scale**2))
        return self.kernel_matrix

if __name__ == "__main__":

    N.random.seed(1)
    data = N.random.rand(4, 2)

    k = Kernel()
    print k
    edm = k.euclidean_distance(data)

    kse = KernelSquaredExponential()
    print kse
    ksem = kse.compute(data)

