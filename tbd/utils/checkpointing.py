from datetime import datetime
import os
import shutil
import subprocess
from typing import Optional, Tuple, Type
import warnings

import torch
from torch import nn, optim


def create_checkpoint_dir(save_dirpath: str, config_ymlpath: str) -> str:
    """
    Given a directory path, creates a sub-directory based on timestamp, and copies over
    config of current experiemnt in that sub-directory, to associate checkpoints with their
    respective config. Moreover, records current commit SHA in a text file.

    Parameters
    ----------
    save_dirpath: str
        Path to directory to save checkpoints into (a sub-directory). Check ``--save-dirpath``
        argument in ``train.py``.
    config_ymlpath: str
        Path to yml config file. Check ``--config-yml`` argument in ``train.py``.

    Returns
    -------
    str
        Path to the sub-directory based on timestamp.
    """

    # create a fresh directory based on timestamp, inside save_dirpath
    save_datetime = datetime.strftime(datetime.now(), "%d-%b-%Y-%H:%M:%S")
    checkpoint_dirpath = os.path.join(save_dirpath, save_datetime)
    os.makedirs(checkpoint_dirpath)

    # copy over currently used config file inside this directory
    shutil.copy(config_ymlpath, checkpoint_dirpath)

    # save current git commit hash in this checkpoint directory
    commit_sha_subprocess = subprocess.Popen(
        ["git", "rev-parse", "--short", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    commit_sha, _ = commit_sha_subprocess.communicate()
    with open(os.path.join(checkpoint_dirpath, "commit_sha.txt"), "w") as commit_sha_file:
        commit_sha_file.write(commit_sha.decode("utf-8").strip().replace("\n", ""))
    return checkpoint_dirpath


def save_checkpoint(checkpoint_dirpath: str,
                    iteration: int,
                    model: Type[nn.Module],
                    optimizer: Type[optim.Optimizer]) -> None:
    """
    Given a path to checkpoint saving directory (the one named by timestamp) and iteration number,
    save state dicts of model and optimizer to a .pth file.

    Parameters
    ----------
    checkpoint_dirpath: str
        Path to checkpoint saving directory (as created by ``create_checkpoint_dir``).
    iteration: int
        Iteration number after which checkpoint is being saved.
    model: Type[nn.Module]
    optimizer: Type[optim.Optimizer]
    """

    if isinstance(model, nn.DataParallel):
        model_state_dict = model.module.state_dict()
    else:
        model_state_dict = model.state_dict()

    torch.save(
        {
            "model": model_state_dict,
            "optimizer": optimizer.state_dict(),
        },
        os.path.join(checkpoint_dirpath, f"model_{iteration}.pth"),
    )


def load_checkpoint(checkpoint_dirpath: str,
                    iteration: int,
                    model: Type[nn.Module],
                    optimizer: Optional[optim.Optimizer] = None
                    ) -> Tuple[nn.Module, optim.Optimizer]:
    """
    Given a path to directory containing saved checkpoints and iteration number, load corresponding
    checkpoint. This method checks if current commit SHA of code matches the commit SHA recorded
    when this checkpoint was saved - raises a warning if they don't match.

    Parameters
    ----------
    checkpoint_dirpath: str
        Path to directory containing saved checkpoints (as created by ``create_checkpoint_dir``).
    iteration: int
        Iteration number for which checkpoint is to be loaded.
    model: Type[nn.Module]
    optimizer: Type[optim.Optimizer]

    Returns
    -------
    Tuple[nn.Module, optim.Optimizer]
        Model and optimizer with loaded parameters from checkpoint.
    """

    # verify commit sha, raise warning if it doesn't match
    current_commit_sha_subprocess = subprocess.Popen(
        ["git", "rev-parse", "--short", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    current_commit_sha, _ = current_commit_sha_subprocess.communicate()
    current_commit_sha = current_commit_sha.decode("utf-8").strip().replace("\n", "")

    with open(os.path.join(checkpoint_dirpath, "commit_sha.txt"), "r") as commit_sha_file:
        checkpoint_commit_sha = commit_sha_file.read().strip().replace("\n", "")

    if current_commit_sha != checkpoint_commit_sha:
        warnings.warn(
            f"Current commit ({current_commit_sha}) and the commit "
            f"({checkpoint_commit_sha}) from which checkpoint was saved,"
            " are different. This might affect reproducibility and results."
        )

    # derive checkpoint name / path from the iteration number
    checkpoint_pthpath = os.path.join(checkpoint_dirpath, f"model_{iteration}.pth")

    # load encoder, decoder, optimizer state_dicts
    components = torch.load(checkpoint_pthpath)

    if isinstance(model, nn.DataParallel):
        model.module.load_state_dict(components["model"])
    else:
        model.load_state_dict(components["model"])

    if optimizer is not None:
        optimizer.load_state_dict(components["optimizer"])
    return model, optimizer
