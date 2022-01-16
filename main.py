""" Created by Dominik Schnaus at 13.12.2021.
Main file to run the training.
"""
from pathlib import Path
from datetime import datetime

import wandb
import yaml
import randomname
from easydict import EasyDict

from wandb.sdk.wandb_run import Run

from gbr.train import train_and_evaluate, get_latest_checkpoint
from gbr.models.faster_rcnn import fasterrcnn_fpn
from gbr.models.yolox import get_model as get_yolox_model


def get_model(model_name: str, **kwargs):
    if "yolo" in model_name.lower():
        model_size = model_name.split("-")[1]  # yolox-l
        opt = EasyDict(
            dict(
                backbone=f"CSPDarknet-{model_size}",
                depth_wise=True if model_size == "nano" else False,
                input_size=(256, 256),
                test_size=(256, 256),
                num_classes=2,
                label_name=["cots"],
                reid_dim=0,
                stride=[8, 16, 32],
                vis_thresh=0.001,
                nms_thresh=0.65,
                tracking_id_nums=None,
                use_amp=False
            )
        )
        return get_yolox_model(opt)
    else:
        return fasterrcnn_fpn(model_name, **kwargs)


if __name__ == '__main__':
    # load config
    with Path("./config.yaml").open("r") as f:
        config = yaml.safe_load(f)

    params = config["params"]

    date_time = datetime.now().replace(microsecond=0).isoformat().replace(':', '_')
    model_name = config["params"]["model_name"]
    run_name = randomname.get_name() + "-" + model_name
    run: Run = wandb.init(entity="rkstgr",
                          project="great-barrier-reef",
                          name=run_name,
                          notes=f"{date_time}",
                          config=params
                          )

    # only log the two right most parts of the file paths
    run.summary["train_file"] = "/".join(config["local"]["train_annotations"].split("/")[-2:])
    run.summary["val_file"] = "/".join(config["local"]["val_annotations"].split("/")[-2:])

    run.summary["model_name"] = model_name

    # get the checkpoint path from the run name and create the folder
    # fallback to date_time if wandb runs in offline mode
    # Path(checkpoints/eager-sunset-100)
    checkpoint_root = Path(config["local"]["checkpoint_root"]).joinpath(run.name if run.name else date_time)
    checkpoint_root.mkdir(exist_ok=True, parents=True)

    # if a checkpoint is given construct it from the checkpoint directory
    if run.resumed:
        existing_checkpoint_path = get_latest_checkpoint(checkpoint_root)
    else:
        existing_checkpoint = config["local"].get("resume_checkpoint", None)
        existing_checkpoint_path = str(checkpoint_root.parent.joinpath(existing_checkpoint)) \
            if existing_checkpoint \
            else None

    # model = fasterrcnn_fpn(model_name, min_size_train=256, max_size_train=256)
    model = get_model(model_name)

    # resnet50: train 512x512 -> batch size 20, val 720x1280 -> batch size 16
    # wide_resnet101_2: train 512x512 -> batch size 13, val 720x1280 -> batch size 16
    # efficientnet_b7: train 512x512 -> batch size 2, val 720x1280 -> batch size 1
    # efficientnet_b0: train 512x512 -> batch size 8, val 720x1280 -> batch size 6

    wandb.watch(model, log_freq=100)

    try:
        train_and_evaluate(
            model=model,
            root=config["local"]["dataset_root"],
            train_annotations_file=config["local"]["train_annotations"],
            val_annotations_file=config["local"]["val_annotations"],
            checkpoint_path=str(checkpoint_root),
            existing_checkpoint_path=existing_checkpoint_path,
            **params
        )
    finally:
        run.finish()
