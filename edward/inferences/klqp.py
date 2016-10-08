from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import six
import tensorflow as tf

from edward.inferences.variational_inference import VariationalInference
from edward.models import RandomVariable, Normal
from edward.util import copy, kl_multivariate_normal


class KLqp(VariationalInference):
  """Variational inference with the KL divergence

  .. math::

    KL( q(z; \lambda) || p(z | x) ).

  This class minimizes the objective by automatically selecting from a
  variety of black box inference techniques.
  """
  def __init__(self, *args, **kwargs):
    super(KLqp, self).__init__(*args, **kwargs)

  def initialize(self, n_samples=1, score=None, *args, **kwargs):
    """Initialization.

    Parameters
    ----------
    n_samples : int, optional
      Number of samples from variational model for calculating
      stochastic gradients.
    score : bool, optional
      Whether to force inference to use the score function
      gradient estimator. Otherwise default is to use the
      reparameterization gradient if available.
    """
    if score is None and \
       all([rv.is_reparameterized and rv.is_continuous
            for rv in six.itervalues(self.latent_vars)]):
      self.score = False
    else:
      self.score = True

    self.n_samples = n_samples
    return super(KLqp, self).initialize(*args, **kwargs)

  def build_loss_and_gradients(self, var_list):
    """Wrapper for the KLqp loss function.

    .. math::

      -ELBO =  -E_{q(z; \lambda)} [ \log p(x, z) - \log q(z; \lambda) ]

    KLqp supports

    1. score function gradients (Paisley et al., 2012)
    2. reparameterization gradients (Kingma and Welling, 2014)

    of the loss function. For both stochastic gradients, it uses
    Rao-Blackwellization for variance reduction.

    If the variational model is a normal distribution and the prior is
    standard normal, then loss function can be written as

    .. math::

      -E_{[\log p(x | z)] + KL( q(z; \lambda) || p(z) ),

    where the KL term is computed analytically (Kingma and Welling,
    2014).
    """
    qz_is_normal = all([isinstance(rv, Normal) for
                       rv in six.itervalues(self.latent_vars)])
    z_is_normal = all([isinstance(rv, Normal) for
                       rv in six.iterkeys(self.latent_vars)])
    is_analytic_kl = qz_is_normal and \
        (z_is_normal or hasattr(self.model_wrapper, 'log_lik'))
    if self.score:
      if is_analytic_kl:
        return build_score_kl_loss_and_gradients(self, var_list)
      # Analytic entropies may lead to problems around
      # convergence; for now it is deactivated.
      # elif is_analytic_entropy:
      #    return build_score_entropy_loss_and_gradients(self, var_list)
      else:
        return build_score_rb_loss_and_gradients(self, var_list)
    else:
      if is_analytic_kl:
        loss = build_reparam_kl_loss(self)
      # elif is_analytic_entropy:
      #    loss = build_reparam_entropy_loss(self)
      else:
        loss = build_reparam_loss(self)

      gradients = tf.gradients(loss, var_list)
      grads_and_vars = [(grad, var) for grad, var in zip(gradients, var_list)]
      return loss, grads_and_vars


MFVI = KLqp  # deprecated synonym


class ReparameterizationKLqp(VariationalInference):
  """Variational inference with the KL divergence

  .. math::

    KL( q(z; \lambda) || p(z | x) ).

  This class minimizes the objective using the reparameterization
  gradient.
  """
  def __init__(self, *args, **kwargs):
    super(ReparameterizationKLqp, self).__init__(*args, **kwargs)

  def initialize(self, n_samples=1, *args, **kwargs):
    """Initialization.

    Parameters
    ----------
    n_samples : int, optional
      Number of samples from variational model for calculating
      stochastic gradients.
    """
    self.n_samples = n_samples
    return super(ReparameterizationKLqp, self).initialize(*args, **kwargs)

  def build_loss(self):
    return build_reparam_loss(self)


class ReparameterizationKLKLqp(VariationalInference):
  """Variational inference with the KL divergence

  .. math::

    KL( q(z; \lambda) || p(z | x) ).

  This class minimizes the objective using the reparameterization
  gradient and an analytic KL term.
  """
  def __init__(self, *args, **kwargs):
    super(ReparameterizationKLKLqp, self).__init__(*args, **kwargs)

  def initialize(self, n_samples=1, *args, **kwargs):
    """Initialization.

    Parameters
    ----------
    n_samples : int, optional
      Number of samples from variational model for calculating
      stochastic gradients.
    """
    self.n_samples = n_samples
    return super(ReparameterizationKLKLqp, self).initialize(*args, **kwargs)

  def build_loss(self):
    return build_reparam_kl_loss(self)


class ReparameterizationEntropyKLqp(VariationalInference):
  """Variational inference with the KL divergence

  .. math::

    KL( q(z; \lambda) || p(z | x) ).

  This class minimizes the objective using the reparameterization
  gradient and an analytic entropy term.
  """
  def __init__(self, *args, **kwargs):
    super(ReparameterizationEntropyKLqp, self).__init__(*args, **kwargs)

  def initialize(self, n_samples=1, *args, **kwargs):
    """Initialization.

    Parameters
    ----------
    n_samples : int, optional
      Number of samples from variational model for calculating
      stochastic gradients.
    """
    self.n_samples = n_samples
    return super(ReparameterizationEntropyKLqp, self).initialize(
        *args, **kwargs)

  def build_loss(self):
    return build_reparam_entropy_loss(self)


class ScoreKLqp(VariationalInference):
  """Variational inference with the KL divergence

  .. math::

    KL( q(z; \lambda) || p(z | x) ).

  This class minimizes the objective using the score function
  gradient.
  """
  def __init__(self, *args, **kwargs):
    super(ScoreKLqp, self).__init__(*args, **kwargs)

  def initialize(self, n_samples=1, *args, **kwargs):
    """Initialization.

    Parameters
    ----------
    n_samples : int, optional
      Number of samples from variational model for calculating
      stochastic gradients.
    """
    self.n_samples = n_samples
    return super(ScoreKLqp, self).initialize(*args, **kwargs)

  def build_loss_and_gradients(self, var_list):
    return build_score_loss_and_gradients(self, var_list)


class ScoreRBKLqp(VariationalInference):
  """Variational inference with the KL divergence

  .. math::

    KL( q(z; \lambda) || p(z | x) ).

  This class minimizes the objective using the score function
  gradient and Rao-Blackwellization.
  """
  def __init__(self, *args, **kwargs):
    super(ScoreRBKLqp, self).__init__(*args, **kwargs)

  def initialize(self, n_samples=1, *args, **kwargs):
    """Initialization.

    Parameters
    ----------
    n_samples : int, optional
      Number of samples from variational model for calculating
      stochastic gradients.
    """
    self.n_samples = n_samples
    return super(ScoreRBKLqp, self).initialize(*args, **kwargs)

  def build_loss_and_gradients(self, var_list):
    return build_score_rb_loss_and_gradients(self, var_list)


class ScoreKLKLqp(VariationalInference):
  """Variational inference with the KL divergence

  .. math::

    KL( q(z; \lambda) || p(z | x) ).

  This class minimizes the objective using the score function gradient
  and an analytic KL term.
  """
  def __init__(self, *args, **kwargs):
    super(ScoreKLKLqp, self).__init__(*args, **kwargs)

  def initialize(self, n_samples=1, *args, **kwargs):
    """Initialization.

    Parameters
    ----------
    n_samples : int, optional
      Number of samples from variational model for calculating
      stochastic gradients.
    """
    self.n_samples = n_samples
    return super(ScoreKLKLqp, self).initialize(*args, **kwargs)

  def build_loss_and_gradients(self, var_list):
    return build_score_kl_loss_and_gradients(self, var_list)


class ScoreEntropyKLqp(VariationalInference):
  """Variational inference with the KL divergence

  .. math::

    KL( q(z; \lambda) || p(z | x) ).

  This class minimizes the objective using the score function gradient
  and an analytic entropy term.
  """
  def __init__(self, *args, **kwargs):
    super(ScoreEntropyKLqp, self).__init__(*args, **kwargs)

  def initialize(self, n_samples=1, *args, **kwargs):
    """Initialization.

    Parameters
    ----------
    n_samples : int, optional
      Number of samples from variational model for calculating
      stochastic gradients.
    """
    self.n_samples = n_samples
    return super(ScoreEntropyKLqp, self).initialize(*args, **kwargs)

  def build_loss_and_gradients(self, var_list):
    return build_score_entropy_loss_and_gradients(self, var_list)


def build_reparam_loss(inference):
  """Build loss function. Its automatic differentiation
  is a stochastic gradient of

  .. math::

    -ELBO =  -E_{q(z; \lambda)} [ \log p(x, z) - \log q(z; \lambda) ]

  based on the reparameterization trick (Kingma and Welling, 2014).

  Computed by sampling from :math:`q(z;\lambda)` and evaluating the
  expectation using Monte Carlo sampling.
  """
  p_log_prob = [0.0] * inference.n_samples
  q_log_prob = [0.0] * inference.n_samples
  for s in range(inference.n_samples):
    z_sample = {}
    for z, qz in six.iteritems(inference.latent_vars):
      # Copy q(z) to obtain new set of posterior samples.
      qz_copy = copy(qz, scope='inference_' + str(s))
      z_sample[z] = qz_copy.value()
      q_log_prob[s] += tf.reduce_sum(qz.log_prob(z_sample[z]))

    if inference.model_wrapper is None:
      # Form dictionary in order to replace conditioning on prior or
      # observed variable with conditioning on posterior sample or
      # observed data.
      dict_swap = z_sample
      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          dict_swap[x] = obs

      for z in six.iterkeys(inference.latent_vars):
        z_copy = copy(z, dict_swap, scope='inference_' + str(s))
        p_log_prob[s] += tf.reduce_sum(z_copy.log_prob(z_sample[z]))

      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          x_copy = copy(x, dict_swap, scope='inference_' + str(s))
          p_log_prob[s] += tf.reduce_sum(x_copy.log_prob(obs))
    else:
      x = inference.data
      p_log_prob[s] = inference.model_wrapper.log_prob(x, z_sample)

  p_log_prob = tf.pack(p_log_prob)
  q_log_prob = tf.pack(q_log_prob)
  loss = -tf.reduce_mean(p_log_prob - q_log_prob)
  return loss


def build_reparam_kl_loss(inference):
  """Build loss function. Its automatic differentiation
  is a stochastic gradient of

  .. math::

    -ELBO =  - ( E_{q(z; \lambda)} [ \log p(x | z) ]
          + KL(q(z; \lambda) || p(z)) )

  based on the reparameterization trick (Kingma and Welling, 2014).

  It assumes the KL is analytic.

  For model wrappers, it assumes the prior is :math:`p(z) =
  \mathcal{N}(z; 0, 1)`.

  Computed by sampling from :math:`q(z;\lambda)` and evaluating the
  expectation using Monte Carlo sampling.
  """
  p_log_lik = [0.0] * inference.n_samples
  for s in range(inference.n_samples):
    z_sample = {}
    for z, qz in six.iteritems(inference.latent_vars):
      # Copy q(z) to obtain new set of posterior samples.
      qz_copy = copy(qz, scope='inference_' + str(s))
      z_sample[z] = qz_copy.value()

    if inference.model_wrapper is None:
      # Form dictionary in order to replace conditioning on prior or
      # observed variable with conditioning on posterior sample or
      # observed data.
      dict_swap = z_sample
      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          dict_swap[x] = obs

      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          x_copy = copy(x, dict_swap, scope='inference_' + str(s))
          p_log_lik[s] += tf.reduce_sum(x_copy.log_prob(obs))
    else:
      x = inference.data
      p_log_lik[s] = inference.model_wrapper.log_lik(x, z_sample)

  p_log_lik = tf.pack(p_log_lik)

  if inference.model_wrapper is None:
    kl = tf.reduce_sum([tf.reduce_sum(kl_multivariate_normal(
                        qz.mu, qz.sigma, z.mu, z.sigma))
                        for z, qz in six.iteritems(inference.latent_vars)])
  else:
    kl = tf.reduce_sum([tf.reduce_sum(kl_multivariate_normal(qz.mu, qz.sigma))
                        for qz in six.itervalues(inference.latent_vars)])

  loss = -(tf.reduce_mean(p_log_lik) - kl)
  return loss


def build_reparam_entropy_loss(inference):
  """Build loss function. Its automatic differentiation
  is a stochastic gradient of

  .. math::

    -ELBO =  -( E_{q(z; \lambda)} [ \log p(x , z) ]
          + H(q(z; \lambda)) )

  based on the reparameterization trick (Kingma and Welling, 2014).

  It assumes the entropy is analytic.

  Computed by sampling from :math:`q(z;\lambda)` and evaluating the
  expectation using Monte Carlo sampling.
  """
  p_log_prob = [0.0] * inference.n_samples
  for s in range(inference.n_samples):
    z_sample = {}
    for z, qz in six.iteritems(inference.latent_vars):
      # Copy q(z) to obtain new set of posterior samples.
      qz_copy = copy(qz, scope='inference_' + str(s))
      z_sample[z] = qz_copy.value()

    if inference.model_wrapper is None:
      # Form dictionary in order to replace conditioning on prior or
      # observed variable with conditioning on posterior sample or
      # observed data.
      dict_swap = z_sample
      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          dict_swap[x] = obs

      for z in six.iterkeys(inference.latent_vars):
        z_copy = copy(z, dict_swap, scope='inference_' + str(s))
        p_log_prob[s] += tf.reduce_sum(z_copy.log_prob(z_sample[z]))

      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          x_copy = copy(x, dict_swap, scope='inference_' + str(s))
          p_log_prob[s] += tf.reduce_sum(x_copy.log_prob(obs))
    else:
      x = inference.data
      p_log_prob[s] = inference.model_wrapper.log_prob(x, z_sample)

  p_log_prob = tf.pack(p_log_prob)

  q_entropy = tf.reduce_sum([qz.entropy()
                             for qz in six.itervalues(inference.latent_vars)])

  loss = -(tf.reduce_mean(p_log_prob) + q_entropy)
  return loss


def build_score_loss_and_gradients(inference, var_list):
  """Build loss function and gradients based on the score function
  estimator (Paisley et al., 2012).

  Computed by sampling from :math:`q(z;\lambda)` and evaluating the
  expectation using Monte Carlo sampling.
  """
  p_log_prob = [0.0] * inference.n_samples
  q_log_prob = [0.0] * inference.n_samples
  for s in range(inference.n_samples):
    z_sample = {}
    for z, qz in six.iteritems(inference.latent_vars):
      # Copy q(z) to obtain new set of posterior samples.
      qz_copy = copy(qz, scope='inference_' + str(s))
      z_sample[z] = qz_copy.value()
      q_log_prob[s] += tf.reduce_sum(
          qz.log_prob(tf.stop_gradient(z_sample[z])))

    if inference.model_wrapper is None:
      # Form dictionary in order to replace conditioning on prior or
      # observed variable with conditioning on posterior sample or
      # observed data.
      dict_swap = z_sample
      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          dict_swap[x] = obs

      for z in six.iterkeys(inference.latent_vars):
        z_copy = copy(z, dict_swap, scope='inference_' + str(s))
        p_log_prob[s] += tf.reduce_sum(z_copy.log_prob(z_sample[z]))

      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          x_copy = copy(x, dict_swap, scope='inference_' + str(s))
          p_log_prob[s] += tf.reduce_sum(x_copy.log_prob(obs))
    else:
      x = inference.data
      p_log_prob[s] = inference.model_wrapper.log_prob(x, z_sample)

  p_log_prob = tf.pack(p_log_prob)
  q_log_prob = tf.pack(q_log_prob)

  losses = p_log_prob - q_log_prob
  loss = -tf.reduce_mean(losses)
  gradients = tf.gradients(
      -tf.reduce_mean(q_log_prob * tf.stop_gradient(losses)),
      var_list)
  grads_and_vars = [(grad, var) for grad, var in zip(gradients, var_list)]
  return loss, grads_and_vars


def build_score_rb_loss_and_gradients(inference, var_list):
  """Build loss function and gradients based on the score function
  estimator (Paisley et al., 2012) and Rao-Blackwellization (Ranganath
  et al., 2014).

  Computed by sampling from :math:`q(z;\lambda)` and evaluating the
  expectation using Monte Carlo sampling.
  """
  # TODO non-MF case, which loops over each variable instead of each
  # variational factor
  #for var in var_list:
  #  qzs = get_descendants(var, list(six.itervalues(inference.latent_vars)))
  # TODO model parameters
  # Build tensors for loss and gradient calculations, one set for each
  # sample from the variational distribution.
  p_log_probs = [{}] * inference.n_samples
  q_log_probs = [{}] * inference.n_samples
  for s in range(inference.n_samples):
    # Build tensors for variational log-densities.
    z_sample = {}
    for z, qz in six.iteritems(inference.latent_vars):
      # Copy q(z) to obtain new set of posterior samples.
      qz_copy = copy(qz, scope='inference_' + str(s))
      z_sample[z] = qz_copy.value()
      q_log_probs[s][z] = tf.reduce_sum(
          qz.log_prob(tf.stop_gradient(z_sample[z])))

    # Form dictionary in order to replace conditioning on prior or
    # observed variable with conditioning on posterior sample or
    # observed data.
    dict_swap = z_sample
    for x, obs in six.iteritems(inference.data):
      if isinstance(x, RandomVariable):
        dict_swap[x] = obs

    # Build tensors for model log-densities.
    for z in six.iterkeys(inference.latent_vars):
      z_copy = copy(z, dict_swap, scope='inference_' + str(s))
      p_log_probs[s][z] = tf.reduce_sum(z_copy.log_prob(z_sample[z]))

    for x, obs in six.iteritems(inference.data):
      if isinstance(x, RandomVariable):
        x_copy = copy(x, dict_swap, scope='inference_' + str(s))
        p_log_probs[s][x] = tf.reduce_sum(x_copy.log_prob(obs))

  # Take gradients for each set of parameters in a variational factor.
  model_rvs = list(six.iterkeys(inference.latent_vars)) + \
              [x for x in six.iterkeys(inference.data)
               if isinstance(x, RandomVariable)]
  grads_and_vars = []
  for z, qz in six.iteritems(inference.latent_vars):
    model_rvs_i = z.get_descendants(model_rvs) + [z]
    pi_log_prob = [0.0] * inference.n_samples
    qi_log_prob = [0.0] * inference.n_samples
    for s in range(inference.n_samples):
      qi_log_prob[s] = tf.reduce_sum([q_log_probs[s][rv] for rv in model_rvs_i
                                      if rv in six.iterkeys(inference.latent_vars)])
      pi_log_prob[s] = tf.reduce_sum([p_log_probs[s][rv] for rv in model_rvs_i])

    pi_log_prob = tf.pack(pi_log_prob)
    qi_log_prob = tf.pack(qi_log_prob)
    qz_vars = qz.get_variables(var_list)
    grads = tf.gradients(
        -tf.reduce_mean(qi_log_prob * tf.stop_gradient(pi_log_prob - qi_log_prob)),
        qz_vars)
    for grad, var in zip(tf.unpack(grads), qz_vars):
      grads_and_vars.append((grad, var))

  loss = -(tf.reduce_sum(list(six.itervalues(p_log_probs[0]))) -
           tf.reduce_sum(list(six.itervalues(q_log_probs[0]))))
  return loss, grads_and_vars


def build_score_kl_loss_and_gradients(inference, var_list):
  """Build loss function and gradients based on the score function
  estimator (Paisley et al., 2012).

  It assumes the KL is analytic.

  For model wrappers, it assumes the prior is :math:`p(z) =
  \mathcal{N}(z; 0, 1)`.

  Computed by sampling from :math:`q(z;\lambda)` and evaluating the
  expectation using Monte Carlo sampling.
  """
  p_log_lik = [0.0] * inference.n_samples
  q_log_prob = [0.0] * inference.n_samples
  for s in range(inference.n_samples):
    z_sample = {}
    for z, qz in six.iteritems(inference.latent_vars):
      # Copy q(z) to obtain new set of posterior samples.
      qz_copy = copy(qz, scope='inference_' + str(s))
      z_sample[z] = qz_copy.value()
      q_log_prob[s] += tf.reduce_sum(
          qz.log_prob(tf.stop_gradient(z_sample[z])))

    if inference.model_wrapper is None:
      # Form dictionary in order to replace conditioning on prior or
      # observed variable with conditioning on posterior sample or
      # observed data.
      dict_swap = z_sample
      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          dict_swap[x] = obs

      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          x_copy = copy(x, dict_swap, scope='inference_' + str(s))
          p_log_lik[s] += tf.reduce_sum(x_copy.log_prob(obs))
    else:
      x = inference.data
      p_log_lik[s] = inference.model_wrapper.log_lik(x, z_sample)

  p_log_lik = tf.pack(p_log_lik)
  q_log_prob = tf.pack(q_log_prob)

  if inference.model_wrapper is None:
    kl = tf.reduce_sum([tf.reduce_sum(kl_multivariate_normal(
                        qz.mu, qz.sigma, z.mu, z.sigma))
                        for z, qz in six.iteritems(inference.latent_vars)])
  else:
    kl = tf.reduce_sum([tf.reduce_sum(kl_multivariate_normal(qz.mu, qz.sigma))
                        for qz in six.itervalues(inference.latent_vars)])

  loss = -(tf.reduce_mean(p_log_lik) - kl)
  gradients = tf.gradients(
      -(tf.reduce_mean(q_log_prob * tf.stop_gradient(p_log_lik)) - kl),
      var_list)
  grads_and_vars = [(grad, var) for grad, var in zip(gradients, var_list)]
  return loss, grads_and_vars


def build_score_entropy_loss_and_gradients(inference, var_list):
  """Build loss function and gradients based on the score function
  estimator (Paisley et al., 2012).

  It assumes the entropy is analytic.

  Computed by sampling from :math:`q(z;\lambda)` and evaluating the
  expectation using Monte Carlo sampling.
  """
  p_log_prob = [0.0] * inference.n_samples
  q_log_prob = [0.0] * inference.n_samples
  for s in range(inference.n_samples):
    z_sample = {}
    for z, qz in six.iteritems(inference.latent_vars):
      # Copy q(z) to obtain new set of posterior samples.
      qz_copy = copy(qz, scope='inference_' + str(s))
      z_sample[z] = qz_copy.value()
      q_log_prob[s] += tf.reduce_sum(
          qz.log_prob(tf.stop_gradient(z_sample[z])))

    if inference.model_wrapper is None:
      # Form dictionary in order to replace conditioning on prior or
      # observed variable with conditioning on posterior sample or
      # observed data.
      dict_swap = z_sample
      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          dict_swap[x] = obs

      for z in six.iterkeys(inference.latent_vars):
        z_copy = copy(z, dict_swap, scope='inference_' + str(s))
        p_log_prob[s] += tf.reduce_sum(z_copy.log_prob(z_sample[z]))

      for x, obs in six.iteritems(inference.data):
        if isinstance(x, RandomVariable):
          x_copy = copy(x, dict_swap, scope='inference_' + str(s))
          p_log_prob[s] += tf.reduce_sum(x_copy.log_prob(obs))
    else:
      x = inference.data
      p_log_prob[s] = inference.model_wrapper.log_prob(x, z_sample)

  p_log_prob = tf.pack(p_log_prob)
  q_log_prob = tf.pack(q_log_prob)

  q_entropy = tf.reduce_sum([qz.entropy()
                             for qz in six.itervalues(inference.latent_vars)])

  loss = -(tf.reduce_mean(p_log_prob) + q_entropy)
  gradients = tf.gradients(
      -(tf.reduce_mean(q_log_prob * tf.stop_gradient(p_log_prob)) +
          q_entropy),
      var_list)
  grads_and_vars = [(grad, var) for grad, var in zip(gradients, var_list)]
  return loss, grads_and_vars
