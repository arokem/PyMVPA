# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   Copyright (c) 2008 Emanuele Olivetti <emanuele@relativita.com> and
#   PyMVPA Team. See COPYING file distributed along with the PyMVPA
#   package for complete list of copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Kernels for Gaussian Process Regression and Classification."""


_DEV__DOC__ = """
Make use of Parameter Collections to keep parameters of the
kernels. Then we would get a uniform .reset() functionality. Now reset
is provided just for parts which are failing in the unittests, but
there is many more places where they are not reset properly if
classifier gets trained on some new data of different dimensionality
"""

__docformat__ = 'restructuredtext'


import numpy as N

from mvpa.misc.state import StateVariable
from mvpa.misc.param import Parameter
from mvpa.misc.exceptions import InvalidHyperparameterError
from mvpa.clfs.distance import squared_euclidean_distance
from mvpa.kernels.base import NumpyKernel
if __debug__:
    from mvpa.base import debug, warning


class ConstantKernel(NumpyKernel):
    """The constant kernel class.
    """

    sigma_0 = Parameter(1.0,
                        doc="""
       A simple constant squared value of which is broadcasted across
       kernel. In the case of GPR -- standard deviation of the Gaussian
       prior probability N(0,sigma_0**2) of the intercept of the
       constant regression.""")

    def _compute(self, data1, data2):
        """Compute kernel matrix.

        :Parameters:
          data1 : numpy.ndarray
            data
          data2 : numpy.ndarray
            data
            (Defaults to None)
        """
        self._k = \
            (self.params.sigma_0 ** 2) * N.ones((data1.shape[0], data2.shape[0]))

    ## def set_hyperparameters(self, hyperparameter):
    ##     if hyperparameter < 0:
    ##         raise InvalidHyperparameterError()
    ##     self.sigma_0 = hyperparameter
    ##     return

    def compute_lml_gradient(self, alphaalphaT_Kinv, data):
        K_grad_sigma_0 = 2*self.params.sigma_0
        # self.lml_gradient = 0.5*(N.trace(N.dot(alphaalphaT_Kinv,K_grad_sigma_0*N.ones(alphaalphaT_Kinv.shape)))
        # Faster formula: N.trace(N.dot(A,B)) = (A*(B.T)).sum()
        # Fastest when B is a constant: B*A.sum()
        self.lml_gradient = 0.5*N.array(K_grad_sigma_0*alphaalphaT_Kinv.sum())
        #return self.lml_gradient

    def compute_lml_gradient_logscale(self, alphaalphaT_Kinv, data):
        K_grad_sigma_0 = 2*self.params.sigma_0**2
        self.lml_gradient = 0.5*N.array(K_grad_sigma_0*alphaalphaT_Kinv.sum())
        #return self.lml_gradient
    pass


class LinearKernel(NumpyKernel):
    """Simple linear kernel
    """
    def _compute(self, d1, d2):
        self._k = N.dot(d1, d2.T)

class PolyKernel(NumpyKernel):
    degree = Parameter(2, doc="Polynomial degree")
    offset = Parameter(1, doc="Offset added to dot product before exponent")
    
    def _compute(self, d1, d2):
        self._k = N.power(N.dot(d1, d2.T) + self.params.offset,
                          self.params.degree)

class RbfKernel(NumpyKernel):
    gamma = Parameter(1.0, allowedtype=float, doc="Scale parameter gamma")
    
    def _compute(self, d1, d2):
        # Calculate squared distance between all points
        Kij = N.dot(d1, d2.T)
        Kii = (d1**2).sum(axis=1).reshape((d1.shape[0], 1))
        Kjj = (d2**2).sum(axis=1).reshape((1, d2.shape[0]))
        d2 = Kii-2*Kij+Kjj
        d2 = N.where(d2 < 0, 0, d2)
        
        # Do the Rbf
        self._k = N.exp(-d2 / self.params.gamma)
        

class GeneralizedLinearKernel(NumpyKernel):
    """The linear kernel class.
    """

    sigma_0 = Parameter(1.0,
                        doc="""
       A simple constant squared value of which is broadcasted across
       kernel. In the case of GPR -- standard deviation of the Gaussian
       prior probability N(0,sigma_0**2) of the intercept of the
       constant regression.""")

    Sigma_p = Parameter(1.0,
                        doc="""
       TODO: generic description.
       In the case of GPR -- scalar or a diagonal of covariance matrix
       of the Gaussian prior probability N(0,Sigma_p) on the weights
       of the linear regression.""")

    gradients = StateVariable(enabled=False,
        doc="Dictionary of gradients per a parameter")

    gradientslog = StateVariable(enabled=False,
        doc="Dictionary of gradients per a parameter in logspace")

    ## def __init__(self, Sigma_p=None, sigma_0=1.0, **kwargs):
    ##     """Initialize the linear kernel instance.

    ##     :Parameters:
    ##       Sigma_p : numpy.ndarray
    ##         Covariance matrix of the Gaussian prior probability N(0,Sigma_p)
    ##         on the weights of the linear regression.
    ##         (Defaults to None)
    ##       sigma_0 : float
    ##         the standard deviation of the Gaussian prior N(0,sigma_0**2)
    ##         of the intercept of the linear regression.
    ##         (Deafults to 1.0)
    ##     """
    ##     # init base class first
    ##     NumpyKernel.__init__(self, **kwargs)

    ##     # TODO: figure out cleaner way... probably by using KernelParameters ;-)
    ##     self.Sigma_p = Sigma_p
    ##     self.sigma_0 = sigma_0


    ## def __repr__(self):
    ##     return "%s(Sigma_p=%s, sigma_0=%s)" \
    ##         % (self.__class__.__name__, str(self.Sigma_p), str(self.sigma_0))

    # XXX ??? would we reset correctly to the original value... model selection
    #     currently depends on this I believe
    def reset(self):
        super(GeneralizedLinearKernel, self).reset()
        self._Sigma_p = self._Sigma_p_orig


    def _compute(self, data1, data2):
        """Compute kernel matrix.
        """
        # it is better to use separate lines of computation, to don't
        # incure computation cost without need (otherwise
        # N.dot(self.Sigma_p, data2.T) can take forever for relatively
        # large number of features)

        Sigma_p = self.params.Sigma_p          # local binding
        sigma_0 = self.params.sigma_0

        #if scalar - scale second term appropriately
        if N.isscalar(Sigma_p):
            if Sigma_p == 1.0:
                data2_sc = data2.T
            else:
                data2_sc = Sigma_p * data2.T

        # if vector use it as diagonal matrix -- ie scale each row by
        # the given value
        elif len(Sigma_p.shape) == 1 and \
                 Sigma_p.shape[0] == data2.shape[1]:
            # which due to numpy broadcasting is the same as product
            # with scalar above
            data2_sc = (Sigma_p * data2).T

        # if it is a full matrix -- full-featured and lengthy
        # matrix product
        else:
            raise ValueError, "Please provide Sigma_p as a scalar or a vector"
            data2_sc = N.dot(Sigma_p, data2.T)
            pass

        # XXX if Sigma_p is changed a warning should be issued!
        # XXX other cases of incorrect Sigma_p could be catched
        self._k = k = N.dot(data1, data2_sc) + sigma_0 ** 2

        # Compute gradients if any was requested
        do_g  = self.states.isEnabled('gradients')
        do_gl = self.states.isEnabled('gradientslog')
        if do_g or do_gl:
            if N.isscalar(Sigma_p):
                g_Sigma_p = N.dot(data1.T, data2)
                gl_Sigma_p = Sigma_p * g_Sigma_p
            else:
                nfeat = len(Sigma_p)
                gsize = (len(data1), len(data2), nfeat)
                if do_g:  g_Sigma_p = N.empty(gsize)
                if do_gl: gl_Sigma_p = N.empty(gsize)
                for i in xrange(nfeat):
                    outer = N.multiply.outer(data1[:, i], data2[:, i])
                    if do_g:  g_Sigma_p[:, :, i] = outer
                    if do_gl: gl_Sigma_p = Sigma_p[i] * outer
            if do_g:
                self.states.gradients = dict(
                    sigma_0=2*sigma_0,
                    Sigma_p=g_Sigma_p)
            if do_gl:
                self.states.gradientslog = dict(
                    sigma_0=2*sigma_0**2,
                    Sigma_p=gl_Sigma_p)
    pass


class ExponentialKernel(NumpyKernel):
    """The Exponential kernel class.

    Note that it can handle a length scale for each dimension for
    Automtic Relevance Determination.

    """

    length_scale = Parameter(1.0, allowedtype='float or ndarray', doc="""
        The characteristic length-scale (or length-scales) of the phenomenon
        under investigation.""")

    sigma_f = Parameter(1.0, allowedtype='float',
        doc="""Signal standard deviation.""")


    ## def __init__(self, length_scale=1.0, sigma_f = 1.0, **kwargs):
    ##     """Initialize an Exponential kernel instance.

    ##     :Parameters:
    ##       length_scale : float OR numpy.ndarray
    ##         the characteristic length-scale (or length-scales) of the
    ##         phenomenon under investigation.
    ##         (Defaults to 1.0)
    ##       sigma_f : float
    ##         Signal standard deviation.
    ##         (Defaults to 1.0)
    ##     """
    ##     # init base class first
    ##     NumpyKernel.__init__(self, **kwargs)

    ##     self.length_scale = length_scale
    ##     self.sigma_f = sigma_f
    ##     self._k = None


    ## def __repr__(self):
    ##     return "%s(length_scale=%s, sigma_f=%s)" \
    ##       % (self.__class__.__name__, str(self.length_scale), str(self.sigma_f))

    def _compute(self, data1, data2):
        """Compute kernel matrix.

        :Parameters:
          data1 : numpy.ndarray
            data
          data2 : numpy.ndarray
            data
            (Defaults to None)
        """
        params = self.params
        # XXX the following computation can be (maybe) made more
        # efficient since length_scale is squared and then
        # square-rooted uselessly.
        # Weighted euclidean distance matrix:
        self.wdm = N.sqrt(squared_euclidean_distance(
            data1, data2, weight=(params.length_scale**-2)))
        self._k = \
            params.sigma_f**2 * N.exp(-self.wdm)

    def gradient(self, data1, data2):
        """Compute gradient of the kernel matrix. A must for fast
        model selection with high-dimensional data.
        """
        raise NotImplementedError

    ## def set_hyperparameters(self, hyperparameter):
    ##     """Set hyperaparmeters from a vector.

    ##     Used by model selection.
    ##     """
    ##     if N.any(hyperparameter < 0):
    ##         raise InvalidHyperparameterError()
    ##     self.sigma_f = hyperparameter[0]
    ##     self.length_scale = hyperparameter[1:]
    ##     return

    def compute_lml_gradient(self,alphaalphaT_Kinv,data):
        """Compute grandient of the kernel and return the portion of
        log marginal likelihood gradient due to the kernel.
        Shorter formula. Allows vector of lengthscales (ARD)
        BUT THIS LAST OPTION SEEMS NOT TO WORK FOR (CURRENTLY)
        UNKNOWN REASONS.
        """
        self.lml_gradient = []
        def lml_grad(K_grad_i):
            # return N.trace(N.dot(alphaalphaT_Kinv,K_grad_i))
            # Faster formula: N.trace(N.dot(A,B)) = (A*(B.T)).sum()
            return (alphaalphaT_Kinv*(K_grad_i.T)).sum()
        grad_sigma_f = 2.0/self.sigma_f*self.kernel_matrix
        self.lml_gradient.append(lml_grad(grad_sigma_f))
        if N.isscalar(self.length_scale) or self.length_scale.size==1:
            # use the same length_scale for all dimensions:
            K_grad_l = self.wdm*self.kernel_matrix*(self.length_scale**-1)
            self.lml_gradient.append(lml_grad(K_grad_l))
        else:
            # use one length_scale for each dimension:
            for i in range(self.length_scale.size):
                K_grad_i = (self.length_scale[i]**-3)*(self.wdm**-1)*self.kernel_matrix*N.subtract.outer(data[:,i],data[:,i])**2
                self.lml_gradient.append(lml_grad(K_grad_i))
                pass
            pass
        self.lml_gradient = 0.5*N.array(self.lml_gradient)
        return self.lml_gradient

    def compute_lml_gradient_logscale(self,alphaalphaT_Kinv,data):
        """Compute grandient of the kernel and return the portion of
        log marginal likelihood gradient due to the kernel.
        Shorter formula. Allows vector of lengthscales (ARD).
        BUT THIS LAST OPTION SEEMS NOT TO WORK FOR (CURRENTLY)
        UNKNOWN REASONS.
        """
        self.lml_gradient = []
        def lml_grad(K_grad_i):
            # return N.trace(N.dot(alphaalphaT_Kinv,K_grad_i))
            # Faster formula: N.trace(N.dot(A,B)) = (A*(B.T)).sum()
            return (alphaalphaT_Kinv*(K_grad_i.T)).sum()
        grad_log_sigma_f = 2.0*self.kernel_matrix
        self.lml_gradient.append(lml_grad(grad_log_sigma_f))
        if N.isscalar(self.length_scale) or self.length_scale.size==1:
            # use the same length_scale for all dimensions:
            K_grad_l = self.wdm*self.kernel_matrix
            self.lml_gradient.append(lml_grad(K_grad_l))
        else:
            # use one length_scale for each dimension:
            for i in range(self.length_scale.size):
                K_grad_i = (self.length_scale[i]**-2)*(self.wdm**-1)*self.kernel_matrix*N.subtract.outer(data[:,i],data[:,i])**2
                self.lml_gradient.append(lml_grad(K_grad_i))
                pass
            pass
        self.lml_gradient = 0.5*N.array(self.lml_gradient)
        return self.lml_gradient

    pass


class SquaredExponentialKernel(NumpyKernel):
    """The Squared Exponential kernel class.

    Note that it can handle a length scale for each dimension for
    Automtic Relevance Determination.

    """
    def __init__(self, length_scale=1.0, sigma_f=1.0, **kwargs):
        """Initialize a Squared Exponential kernel instance.

        :Parameters:
          length_scale : float OR numpy.ndarray
            the characteristic length-scale (or length-scales) of the
            phenomenon under investigation.
            (Defaults to 1.0)
          sigma_f : float
            Signal standard deviation.
            (Defaults to 1.0)
        """
        # init base class first
        NumpyKernel.__init__(self, **kwargs)

        self.length_scale = length_scale
        self.sigma_f = sigma_f

    # XXX ??? 
    def reset(self):
        super(SquaredExponentialKernel, self).reset()
        self._length_scale = self._length_scale_orig


    def __repr__(self):
        return "%s(length_scale=%s, sigma_f=%s)" \
          % (self.__class__.__name__, str(self.length_scale), str(self.sigma_f))

    def _compute(self, data1, data2):
        """Compute kernel matrix.

        :Parameters:
          data1 : numpy.ndarray
            data
          data2 : numpy.ndarray
            data
            (Defaults to None)
        """
        # weighted squared euclidean distance matrix:
        self.wdm2 = squared_euclidean_distance(data1, data2, weight=(self.length_scale**-2))
        self._k = self.sigma_f**2 * N.exp(-0.5*self.wdm2)
        # XXX EO: old implementation:
        # self.kernel_matrix = \
        #     self.sigma_f * N.exp(-squared_euclidean_distance(
        #         data1, data2, weight=0.5 / (self.length_scale ** 2)))

    def set_hyperparameters(self, hyperparameter):
        """Set hyperaparmeters from a vector.

        Used by model selection.
        """
        if N.any(hyperparameter < 0):
            raise InvalidHyperparameterError()
        self.sigma_f = hyperparameter[0]
        self._length_scale = hyperparameter[1:]
        return

    def compute_lml_gradient(self,alphaalphaT_Kinv,data):
        """Compute grandient of the kernel and return the portion of
        log marginal likelihood gradient due to the kernel.
        Shorter formula. Allows vector of lengthscales (ARD).
        """
        self.lml_gradient = []
        def lml_grad(K_grad_i):
            # return N.trace(N.dot(alphaalphaT_Kinv,K_grad_i))
            # Faster formula: N.trace(N.dot(A,B)) = (A*(B.T)).sum()
            return (alphaalphaT_Kinv*(K_grad_i.T)).sum()
        grad_sigma_f = 2.0/self.sigma_f*self.kernel_matrix
        self.lml_gradient.append(lml_grad(grad_sigma_f))
        if N.isscalar(self.length_scale) or self.length_scale.size==1:
            # use the same length_scale for all dimensions:
            K_grad_l = self.wdm2*self.kernel_matrix*(1.0/self.length_scale)
            self.lml_gradient.append(lml_grad(K_grad_l))
        else:
            # use one length_scale for each dimension:
            for i in range(self.length_scale.size):
                K_grad_i = 1.0/(self.length_scale[i]**3)*self.kernel_matrix*N.subtract.outer(data[:,i],data[:,i])**2
                self.lml_gradient.append(lml_grad(K_grad_i))
                pass
            pass
        self.lml_gradient = 0.5*N.array(self.lml_gradient)
        return self.lml_gradient

    def compute_lml_gradient_logscale(self,alphaalphaT_Kinv,data):
        """Compute grandient of the kernel and return the portion of
        log marginal likelihood gradient due to the kernel.
        Hyperparameters are in log scale which is sometimes more
        stable. Shorter formula. Allows vector of lengthscales (ARD).
        """
        self.lml_gradient = []
        def lml_grad(K_grad_i):
            # return N.trace(N.dot(alphaalphaT_Kinv,K_grad_i))
            # Faster formula: N.trace(N.dot(A,B)) = (A*(B.T)).sum()
            return (alphaalphaT_Kinv*(K_grad_i.T)).sum()
        K_grad_log_sigma_f = 2.0*self.kernel_matrix
        self.lml_gradient.append(lml_grad(K_grad_log_sigma_f))
        if N.isscalar(self.length_scale) or self.length_scale.size==1:
            # use the same length_scale for all dimensions:
            K_grad_log_l = self.wdm2*self.kernel_matrix
            self.lml_gradient.append(lml_grad(K_grad_log_l))
        else:
            # use one length_scale for each dimension:
            for i in range(self.length_scale.size):
                K_grad_log_l_i = 1.0/(self.length_scale[i]**2)*self.kernel_matrix*N.subtract.outer(data[:,i],data[:,i])**2
                self.lml_gradient.append(lml_grad(K_grad_log_l_i))
                pass
            pass
        self.lml_gradient = 0.5*N.array(self.lml_gradient)
        return self.lml_gradient

    def _setlength_scale(self, v):
        """Set value of length_scale and its _orig
        """
        self._length_scale = self._length_scale_orig = v

    length_scale = property(fget=lambda x:x._length_scale,
                            fset=_setlength_scale)
    pass

class Matern_3_2Kernel(NumpyKernel):
    """The Matern kernel class for the case ni=3/2 or ni=5/2.

    Note that it can handle a length scale for each dimension for
    Automtic Relevance Determination.

    """
    def __init__(self, length_scale=1.0, sigma_f=1.0, numerator=3.0, **kwargs):
        """Initialize a Squared Exponential kernel instance.

        :Parameters:
          length_scale : float OR numpy.ndarray
            the characteristic length-scale (or length-scales) of the
            phenomenon under investigation.
            (Defaults to 1.0)
          sigma_f : float
            Signal standard deviation.
            (Defaults to 1.0)
          numerator: float
            the numerator of parameter ni of Matern covariance functions.
            Currently only numerator=3.0 and numerator=5.0 are implemented.
            (Defaults to 3.0)
        """
        # init base class first
        NumpyKernel.__init__(self, **kwargs)

        self.length_scale = length_scale
        self.sigma_f = sigma_f
        if numerator == 3.0 or numerator == 5.0:
            self.numerator = numerator
        else:
            raise NotImplementedError

    def __repr__(self):
        return "%s(length_scale=%s, ni=%d/2)" \
            % (self.__class__.__name__, str(self.length_scale), self.numerator)

    def _compute(self, data1, data2):
        """Compute kernel matrix.

        :Parameters:
          data1 : numpy.ndarray
            data
          data2 : numpy.ndarray
            data
            (Defaults to None)
        """
        tmp = squared_euclidean_distance(
                data1, data2, weight=0.5 / (self.length_scale ** 2))
        if self.numerator == 3.0:
            tmp = N.sqrt(tmp)
            self._k = \
                self.sigma_f**2 * (1.0 + N.sqrt(3.0) * tmp) \
                * N.exp(-N.sqrt(3.0) * tmp)
        elif self.numerator == 5.0:
            tmp2 = N.sqrt(tmp)
            self._k = \
                self.sigma_f**2 * (1.0 + N.sqrt(5.0) * tmp2 + 5.0 / 3.0 * tmp) \
                * N.exp(-N.sqrt(5.0) * tmp2)


    def gradient(self, data1, data2):
        """Compute gradient of the kernel matrix. A must for fast
        model selection with high-dimensional data.
        """
        # TODO SOON
        # grad = ...
        # return grad
        raise NotImplementedError

    def set_hyperparameters(self, hyperparameter):
        """Set hyperaparmeters from a vector.

        Used by model selection.
        Note: 'numerator' is not considered as an hyperparameter.
        """
        if N.any(hyperparameter < 0):
            raise InvalidHyperparameterError()
        self.sigma_f = hyperparameter[0]
        self.length_scale = hyperparameter[1:]
        return

    pass


class Matern_5_2Kernel(Matern_3_2Kernel):
    """The Matern kernel class for the case ni=5/2.

    This kernel is just Matern_3_2Kernel(numerator=5.0).
    """
    def __init__(self, **kwargs):
        """Initialize a Squared Exponential kernel instance.

        :Parameters:
          length_scale : float OR numpy.ndarray
            the characteristic length-scale (or length-scales) of the
            phenomenon under investigation.
            (Defaults to 1.0)
        """
        Matern_3_2Kernel.__init__(self, numerator=5.0, **kwargs)
        pass


class RationalQuadraticKernel(NumpyKernel):
    """The Rational Quadratic (RQ) kernel class.

    Note that it can handle a length scale for each dimension for
    Automtic Relevance Determination.

    """
    def __init__(self, length_scale=1.0, sigma_f=1.0, alpha=0.5, **kwargs):
        """Initialize a Squared Exponential kernel instance.

        :Parameters:
          length_scale : float OR numpy.ndarray
            the characteristic length-scale (or length-scales) of the
            phenomenon under investigation.
            (Defaults to 1.0)
          sigma_f : float
            Signal standard deviation.
            (Defaults to 1.0)
          alpha: float
            The parameter of the RQ functions family.
            (Defaults to 2.0)
        """
        # init base class first
        NumpyKernel.__init__(self, **kwargs)

        self.length_scale = length_scale
        self.sigma_f = sigma_f
        self.alpha = alpha

    def __repr__(self):
        return "%s(length_scale=%s, alpha=%f)" \
            % (self.__class__.__name__, str(self.length_scale), self.alpha)

    def _compute(self, data1, data2):
        """Compute kernel matrix.

        :Parameters:
          data1 : numpy.ndarray
            data
          data2 : numpy.ndarray
            data
            (Defaults to None)
        """
        tmp = squared_euclidean_distance(
                data1, data2, weight=1.0 / (self.length_scale ** 2))
        self._k = \
            self.sigma_f**2 * (1.0 + tmp / (2.0 * self.alpha)) ** -self.alpha

    def gradient(self, data1, data2):
        """Compute gradient of the kernel matrix. A must for fast
        model selection with high-dimensional data.
        """
        # TODO SOON
        # grad = ...
        # return grad
        raise NotImplementedError

    def set_hyperparameters(self, hyperparameter):
        """Set hyperaparmeters from a vector.

        Used by model selection.
        Note: 'alpha' is not considered as an hyperparameter.
        """
        if N.any(hyperparameter < 0):
            raise InvalidHyperparameterError()
        self.sigma_f = hyperparameter[0]
        self.length_scale = hyperparameter[1:]
        return

    pass


# dictionary of avalable kernels with names as keys:
kernel_dictionary = {'constant': ConstantKernel,
                     'linear': GeneralizedLinearKernel,
                     'exponential': ExponentialKernel,
                     'squared exponential': SquaredExponentialKernel,
                     'Matern ni=3/2': Matern_3_2Kernel,
                     'Matern ni=5/2': Matern_5_2Kernel,
                     'rational quadratic': RationalQuadraticKernel}

