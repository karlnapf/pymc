'''
Created on Mar 7, 2011

@author: johnsalvatier
'''
from point import *
from types import *

from theano import theano, tensor as t, function
from theano.gof.graph import inputs

import numpy as np 
from functools import wraps

__all__ = ['Model', 'compilef', 'gradient', 'hessian', 'withmodel'] 



class Context(object): 
    def __enter__(self): 
        type(self).contexts.append(self)
        return self

    def __exit__(self, typ, value, traceback):
        type(self).contexts.pop()

def withcontext(contexttype, arg):
    def decorator(fn):
        n = list(fn.func_code.co_varnames).index(arg)

        @wraps(fn)
        def nfn(*args, **kwargs):
            if not (len(args) > n and isinstance(arg[n], contexttype)):
                context = contexttype.get_context()
                args = args[:n] + (context,) + args[n:]
            return fn(*args,**kwargs) 

        return nfn 
    return decorator


class Model(Context):
    """
    Base class for encapsulation of the variables and 
    likelihood factors of a model.
    """

    contexts = []
    @staticmethod
    def get_context():
        return Model.contexts[-1]

    def __init__(self):
        self.vars = []
        self.factors = []
    
    @property
    def logp(model):
        """
        log-probability of the model
            
        Parameters
        ----------
            
        model : Model  

        Returns
        -------

        logp : Theano scalar
            
        """
        return t.add(*map(t.sum, model.factors))

    @property
    def logpc(model): 
        return compilef(model.logp)

    def dlogpc(model, vars = None): 
        return compilef(gradient(model.logp, vars))

    def d2logpc(model, vars = None):
        return compilef(hessian(model.logp, vars))

    @property
    def test_point(self):
        return Point( (var, var.tag.test_value) for var in self.vars)

    @property
    def cont_vars(model):
        return typefilter(model.vars, continuous_types) 

    """
    these functions add random variables
    """
    def Data(model, data, dist):
        args = map(t.constant, as_iterargs(data))
        model.factors.append(dist.logp(*args))

    def Var(model, name, dist):
        var = dist.makevar(name)

        model.vars.append(var)
        model.factors.append(dist.logp(var))
        return var

    def TransformedVar(model, name, dist, trans): 
        tvar = model.Var(trans.name + '_' + name, trans.apply(dist)) 
        return trans.backward(tvar), tvar

withmodel = withcontext(Model, 'model')


def compilef(outs, mode = None):
    return PointFunc(
                function(inputvars(outs), outs, 
                         allow_input_downcast = True, 
                         on_unused_input = 'ignore',
                         mode = mode)
           )


def as_iterargs(data):
    if isinstance(data, tuple): 
        return data
    if hasattr(data, 'columns'): #data frames
        return [np.asarray(data[c]) for c in data.columns] 
    else:
        return [data]

def makeiter(a): 
    if isinstance(a, (tuple, list)):
        return a
    else :
        return [a]

def inputvars(a): 
    return [v for v in inputs(makeiter(a)) if isinstance(v, t.TensorVariable)]

"""
Theano derivative functions 
""" 

def cont_inputs(f):
    return typefilter(inputvars(f), continuous_types)

def gradient1(f, v):
    """flat gradient of f wrt v"""
    return t.flatten(t.grad(f, v))

def gradient(f, vars = None):
    if not vars: 
        vars = cont_inputs(f)

    return t.concatenate([gradient1(f, v) for v in vars], axis = 0)

def jacobian1(f, v):
    """jacobian of f wrt v"""
    f = t.flatten(f)
    idx = t.arange(f.shape[0])
    
    def grad_i(i): 
        return gradient1(f[i], v)

    return theano.map(grad_i, idx)[0]

def jacobian(f, vars = None):
    if not vars: 
        vars = cont_inputs(f)

    return t.concatenate([jacobian1(f, v) for v in vars], axis = 1)

def hessian(f, vars = None):
    return -jacobian(gradient(f, vars), vars)


#theano stuff 
theano.config.warn.sum_div_dimshuffle_bug = False
theano.config.compute_test_value = 'raise'