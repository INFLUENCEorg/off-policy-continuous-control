import os
import gin
import csv

import numpy as np
import torch
from gym.wrappers import Monitor

from basics.replay_buffer import ReplayBuffer, Transition

BASE_LOG_DIR = '../results'


def generate_log_dir(env_name, algo_name, run_id) -> str:
    return f'{BASE_LOG_DIR}/{env_name}/{algo_name}/{run_id}'


def test_for_one_episode(env, algorithm) -> tuple:
    state, done, episode_return, episode_len = env.reset(), False, 0, 0
    while not done:
        action = algorithm.act(state, deterministic=True)
        state, reward, done, _ = env.step(action)
        episode_return += reward
        episode_len += 1
    return episode_len, episode_return


def visualize_trained_policy(
        env_fn,
        algorithm,
        log_dir,
        num_videos
) -> None:
    algorithm.load_actor(log_dir)

    for i in range(num_videos):
        env = Monitor(
            env_fn(),
            directory=f'{log_dir}/videos/{i}'
        )
        test_for_one_episode(env, algorithm)


@gin.configurable(module=__name__)
def train(
        env_fn,
        algorithm,
        buffer: ReplayBuffer,
        log_dir,
        max_steps_per_episode=gin.REQUIRED,
        num_epochs=gin.REQUIRED,  # TODO: all configurable arugments are default to None
        num_steps_per_epoch=gin.REQUIRED,
        update_every=gin.REQUIRED,
        # number of environment interactions between gradient updates; the ratio of the two is locked to 1-to-1.
        num_test_episodes_per_epoch=gin.REQUIRED,
        update_after=gin.REQUIRED,  # for exploration
) -> None:

    # ===== logging =====

    os.makedirs(log_dir, exist_ok=True)

    csv_file = open(f'{log_dir}/progress.csv', 'w+')
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(['epoch', 'test_mean_ep_len', 'test_mean_ep_ret'])

    # ===================

    env = env_fn()
    test_env = env_fn()

    state = env.reset()
    episode_len = 0

    """Follow from OpenAI Spinup's training loop style"""
    total_steps = num_steps_per_epoch * num_epochs

    for t in range(total_steps):

        if t >= update_after:  # num_exploration_steps have passed
            action = algorithm.act(state, deterministic=False)
        else:
            action = env.action_space.sample()

        next_state, reward, done, _ = env.step(action)
        episode_len += 1

        # ignore the done flag if done is caused by hitting the maximum episode steps
        # TODO: environment needs to be wrapped by TimeLimit wrapper
        # however, the little catch is that the environment might actually be done
        # due to termination rather than timeout, but this is much less likely
        # so we just do it this way for convenience

        done = False if episode_len == max_steps_per_episode else done

        buffer.push(Transition(state, action, reward, next_state, done))

        state = next_state

        # end of trajectory handling
        if done or (episode_len == max_steps_per_episode):
            # TODO: talk about termination handling
            state, episode_return, episode_len = env.reset(), 0, 0

        # update handling
        if t >= update_after and (t + 1) % update_every == 0:
            for j in range(update_every):
                batch = buffer.sample()
                algorithm.update_networks(batch)

        # end of epoch handling
        if (t + 1) % num_steps_per_epoch == 0:

            epoch = (t + 1) // num_steps_per_epoch
            episode_lens, episode_returns = [], []

            for j in range(num_test_episodes_per_epoch):
                episode_len, episode_return = test_for_one_episode(test_env, algorithm)
                episode_lens.append(episode_len)
                episode_returns.append(episode_return)

            mean_episode_len = np.mean(episode_lens)
            mean_episode_return = np.mean(episode_returns)

            csv_writer.writerow([epoch, mean_episode_len, mean_episode_return])

            # 9 = 1 for sign + 5 for int + 1 for decimal point + 2 for decimal places
            print(f'Epoch {epoch:4.0f} | Ep len {mean_episode_len:5.0f} | Ep ret {mean_episode_return:9.2f}')

    csv_file.close()
    algorithm.save_actor(log_dir)