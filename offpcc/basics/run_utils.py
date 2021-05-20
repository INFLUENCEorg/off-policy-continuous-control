import gin
import csv
import time
import datetime
import os
import wandb
import csv

import numpy as np
from gym.wrappers import Monitor

from basics.replay_buffer import ReplayBuffer, Transition

BASE_LOG_DIR = '../results'


def make_log_dir(env_name, algo_name, run_id) -> str:
    log_dir = f'{BASE_LOG_DIR}/{env_name}/{algo_name}/{run_id}'
    return log_dir


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
            directory=f'{log_dir}/videos/{i+1}',
            force=True
        )
        test_for_one_episode(env, algorithm)


@gin.configurable(module=__name__)
def train(
        env_fn,
        algorithm,
        buffer: ReplayBuffer,
        max_steps_per_episode=gin.REQUIRED,
        num_epochs=gin.REQUIRED,
        num_steps_per_epoch=gin.REQUIRED,
        update_every=gin.REQUIRED,  # number of env interactions between grad updates; but the ratio is locked to 1-to-1
        num_test_episodes_per_epoch=gin.REQUIRED,
        update_after=gin.REQUIRED,  # for exploration; no update; random action from action space
) -> None:

    """Follow from OpenAI Spinup's training loop style"""

    # prepare for logging (csv)

    csv_file = open(f'{wandb.run.dir}/progress.csv', 'w+')
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow([
        'epoch',
        'timestep',  # number of env interactions OR grad updates (both are equivalent; ratio 1:1)
        'train_ep_len',  # averaged across epoch
        'train_ep_ret',  # averaged across epoch
        'test_ep_len',  # averaged across epoch
        'test_ep_ret',  # averaged across epoch
    ])

    # prepare stats trackers

    episode_len = 0
    episode_ret = 0
    train_episode_lens = []
    train_episode_rets = []
    algo_specific_stats_tracker = []

    total_steps = num_steps_per_epoch * num_epochs

    start_time = time.perf_counter()

    # prepare environments

    env = env_fn()
    test_env = env_fn()

    state = env.reset()

    # training loop

    for t in range(total_steps):

        if t >= update_after:  # exploration is done
            action = algorithm.act(state, deterministic=False)
        else:
            action = env.action_space.sample()

        next_state, reward, done, _ = env.step(action)
        episode_len += 1
        episode_ret += reward

        # Ignore the done flag if done is caused by hitting the maximum episode steps.
        # However, the little catch is that the environment might actually be done
        # due to termination rather than timeout, but this is much less likely
        # so we just do it this way for convenience.

        cutoff = episode_len == max_steps_per_episode
        done = False if cutoff else done

        buffer.push(Transition(state, action, reward, next_state, done))

        state = next_state  # crucial, crucial step

        # end of trajectory handling
        if done or cutoff:
            train_episode_lens.append(episode_len)
            train_episode_rets.append(episode_ret)
            state, episode_len, episode_ret = env.reset(), 0, 0  # reset state and stats trackers

        # update handling
        if t >= update_after and (t + 1) % update_every == 0:
            for j in range(update_every):
                batch = buffer.sample()
                algo_specific_stats = algorithm.update_networks(batch)
                algo_specific_stats_tracker.append(algo_specific_stats)

        # end of epoch handling
        if (t + 1) % num_steps_per_epoch == 0:

            epoch = (t + 1) // num_steps_per_epoch

            # algo specific stats

            algo_specific_stats_over_epoch = {}

            if len(algo_specific_stats_tracker) != 0:
                keys = algo_specific_stats_tracker[0].keys()  # get keys from the first one; all dicts SHOULD share the same keys
                for k in keys:
                    values = []
                    for dictionary in algo_specific_stats_tracker:
                        values.append(dictionary[k])
                    algo_specific_stats_over_epoch[k] = np.mean(values)
                algo_specific_stats_tracker = []

            # training stats

            mean_train_episode_len = np.mean(train_episode_lens)
            mean_train_episode_ret = np.mean(train_episode_rets)

            train_episode_lens = []
            train_episode_rets = []

            # testing stats

            test_episode_lens, test_episode_returns = [], []

            for j in range(num_test_episodes_per_epoch):
                test_episode_len, test_episode_return = test_for_one_episode(test_env, algorithm)
                test_episode_lens.append(test_episode_len)
                test_episode_returns.append(test_episode_return)

            mean_test_episode_len = np.mean(test_episode_lens)
            mean_test_episode_ret = np.mean(test_episode_returns)

            # time-related stats

            epoch_end_time = time.perf_counter()
            time_elapsed = epoch_end_time - start_time  # in seconds
            avg_time_per_epoch = time_elapsed / epoch  # in seconds
            num_epochs_to_go = num_epochs - epoch
            time_to_go = int(num_epochs_to_go * avg_time_per_epoch)  # in seconds
            time_to_go_readable = str(datetime.timedelta(seconds=time_to_go))

            # actually record / print the stats

            # (wandb logging)

            dict_for_wandb = {
                'epoch': epoch,
                'timestep': t+1,
                'train_ep_len': mean_train_episode_len,
                'train_ep_ret': mean_train_episode_ret,
                'test_ep_len': mean_test_episode_len,
                'test_ep_ret': mean_test_episode_ret,
            }
            dict_for_wandb.update(algo_specific_stats_over_epoch)

            wandb.log(dict_for_wandb)

            # (csv logging - will be uploaded to wandb at the very end)

            csv_writer.writerow([
                epoch,
                t + 1,
                mean_train_episode_len,
                mean_train_episode_ret,
                mean_test_episode_len,
                mean_test_episode_ret,
            ])

            # (console logging)

            stats_string = (
                f"===============================================================\n"
                f"| Epoch        | {epoch}\n"
                f"| Timestep     | {t+1}\n"
                f"| Train ep len | {round(mean_train_episode_len, 2)}\n"
                f"| Train ep ret | {round(mean_train_episode_ret, 2)}\n"
                f"| Test ep len  | {round(mean_test_episode_len, 2)}\n"
                f"| Test ep ret  | {round(mean_test_episode_ret, 2)}\n"
                f"| Time rem     | {time_to_go_readable}\n"
                f"==============================================================="
            )  # this is a weird syntax trick but it just creates a single string
            print(stats_string)

    # save stats and model after training loop finishes
    algorithm.save_networks(wandb.run.dir)  # will get uploaded to cloud after script finishes
    csv_file.close()