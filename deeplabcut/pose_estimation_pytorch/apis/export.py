#
# DeepLabCut Toolbox (deeplabcut.org)
# © A. & M.W. Mathis Labs
# https://github.com/DeepLabCut/DeepLabCut
#
# Please see AUTHORS for contributors.
# https://github.com/DeepLabCut/DeepLabCut/blob/main/AUTHORS
#
# Licensed under GNU Lesser General Public License v3.0
#
"""Code to export DeepLabCut models for DLCLive inference"""
import copy
from pathlib import Path

import torch

import deeplabcut.pose_estimation_pytorch.apis.utils as utils
import deeplabcut.pose_estimation_pytorch.data as dlc3_data
from deeplabcut.pose_estimation_pytorch.task import Task


def export_model(
    config: str | Path,
    shuffle: int = 1,
    trainingsetindex: int = 0,
    snapshotindex: int | None = None,
    detector_snapshot_index: int | None = None,
    iteration: int = None,
    overwrite: bool = False,
    wipe_paths: bool = False,
    modelprefix: str = "",
):
    """Export DeepLabCut models for live inference.

    Saves the pytorch_config.yaml configuration, snapshot files, of the model to a
    directory named exported-models-pytorch within the project directory.

    Args:
        config: Path of the project configuration file
        shuffle : The shuffle of the model to export.
        trainingsetindex: The index of the training fraction for the model you wish to
            export.
        snapshotindex: The snapshot index for the weights you wish to export. If None,
            uses the snapshotindex as defined in ``config.yaml``.
        detector_snapshot_index: Only for TD models. If defined, uses the detector with
            the given index for pose estimation. If None, uses the snapshotindex as
            defined in the project ``config.yaml``.
        iteration: The project iteration (active learning loop) you wish to export. If
            None, the iteration listed in the project config file is used.
        overwrite : bool, optional
            If the model you wish to export has already been exported, whether to
            overwrite. default = False
        wipe_paths : bool, optional
            Removes the actual path of your project and the init_weights from the
            ``pytorch_config.yaml``.
        modelprefix: Directory containing the deeplabcut models to use when evaluating
            the network. By default, the models are assumed to exist in the project
            folder.

    Raises:
        ValueError: If a top-down model is exported but no detector snapshots are found.

    Examples:
        Export the last stored snapshot for model trained with shuffle 3:
        >>> import deeplabcut
        >>> deeplabcut.export_model(
        >>>     "/analysis/project/reaching-task/config.yaml",
        >>>     shuffle=3,
        >>>     snapshotindex=-1,
        >>> )
    """
    if iteration is not None:
        raise ValueError(f"TODO(niels)")

    loader = dlc3_data.DLCLoader(
        config=Path(config),
        trainset_index=trainingsetindex,
        shuffle=shuffle,
        modelprefix=modelprefix,
    )

    # FIXME(niels): use loader.pose_task when integrated
    pose_task = Task(loader.model_cfg["method"])

    if snapshotindex is None:
        snapshotindex = loader.project_cfg["snapshotindex"]
    snapshots = utils.get_model_snapshots(snapshotindex, loader.model_folder, pose_task)

    if len(snapshots) == 0:
        raise ValueError(
            f"Could not find any snapshots to export in ``{loader.model_folder}`` for "
            f"``snapshotindex={snapshotindex}``."
        )

    detector_snapshots = [None]
    if pose_task == Task.TOP_DOWN:
        if detector_snapshot_index is None:
            detector_snapshot_index = loader.project_cfg["detector_snapshot_index"]
        detector_snapshots = utils.get_model_snapshots(
            detector_snapshot_index, loader.model_folder, Task.DETECT
        )

        if len(detector_snapshots) == 0:
            raise ValueError(
                "Attempting to export a top-down pose estimation model but no detector"
                f"snapshots were found in ``{loader.model_folder}`` for "
                f"``detector_snapshot_index={detector_snapshot_index}``. You must "
                f"export a detector snapshot with a top-down pose estimation model."
            )

    export_dir_name = (
        f"DLC_{loader.project_cfg['task']}_{loader.model_cfg['net_type']}_"
        f"iteration-{loader.project_cfg['iteration']}_shuffle-{shuffle}"
    )
    export_dir = loader.project_path / "exported-models-pytorch" / export_dir_name
    export_dir.mkdir(exist_ok=True, parents=True)

    load_kwargs = dict(map_location="cpu", weights_only=True)
    for det_snapshot in detector_snapshots:
        detector_weights = None
        if det_snapshot is not None:
            detector_weights = torch.load(det_snapshot.path, **load_kwargs)["model"]

        for snapshot in snapshots:
            export_filename = export_dir_name
            if det_snapshot is not None:
                export_filename += "_" + det_snapshot.uid()
            export_filename += "_" + snapshot.uid()
            export_path = export_dir / export_filename
            if export_path.exists() and not overwrite:
                continue

            model_cfg = copy.deepcopy(loader.model_cfg)
            if wipe_paths:
                model_cfg["metadata"]["project_path"] = ""
                model_cfg["metadata"]["pose_config_path"] = ""
                if "weight_init" in model_cfg["train_settings"]:
                    model_cfg["train_settings"]["weight_init"] = None
                if "resume_training_from" in model_cfg:
                    model_cfg["resume_training_from"] = None
                if "resume_training_from" in model_cfg.get("detector", {}):
                    model_cfg["detector"]["resume_training_from"] = None

            pose_weights = torch.load(snapshot.path, **load_kwargs)["model"]
            export_dict = dict(config=model_cfg, pose=pose_weights)
            if detector_weights is not None:
                export_dict["detector"] = detector_weights

            torch.save(export_dict, export_path)
