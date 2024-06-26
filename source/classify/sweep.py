import wandb
import argparse
import pandas as pd
from sklearn.model_selection import train_test_split

from source.utils.utils import (
    load_config,
    get_cross_val_splits_dir_path,
)
from source.classify import train_and_test_loop


def make_train_tune_split(config):
    config.update(config["sweep"]["general_settings"])
    config["mode"] = "sweep"

    manifest = pd.read_csv(config["manifest_file_path"]).set_index("slide_id")

    for characteristic, groups in config["subgroups"].items():
        manifest = manifest[manifest[characteristic].isin(groups)]

    manifest = manifest[[config["target"]]]
    manifest = manifest.dropna()

    train_manifest, tune_manifest = train_test_split(
        manifest,
        test_size=0.25,
        random_state=config["seed"],
        stratify=manifest[config["target"]],
    )

    save_dir = get_cross_val_splits_dir_path(config) / "fold_0"
    save_dir.mkdir(exist_ok=True, parents=True)

    train_manifest.to_csv(save_dir / "train.csv")
    tune_manifest.to_csv(save_dir / "tune.csv")


def make_wandb_sweep_config(config):
    sweep_config = {
        "method": config["method"],
        "metric": {
            "name": f"fold_0/{config['sweep']['general_settings']['targets'][0]}val_auc",
            "goal": "maximize",
        },
    }

    parameters = {"output_dir": {"values": [config["output_dir"]]}}

    for parameter, value in config["sweep"]["general_settings"].items():
        parameters[parameter] = {"values": [value]}

    for parameter, value in config["sweep"]["fixed_hyperparameters"].items():
        parameters[parameter] = {"values": [value]}

    for parameter, values in config["sweep"]["variable_hyperparameters"].items():
        parameters[parameter] = {"values": values}

    sweep_config["parameters"] = parameters

    return sweep_config


def evaluate_configuration():
    wandb.init()

    wandb.config["mode"] = "sweep"
    wandb.config["n_folds"] = 1

    wandb.config["extraction_level"] = int(
        wandb.config["level_and_extractor"].split("_extractor")[0].split("=")[1]
    )
    wandb.config["extractor_model"] = wandb.config["level_and_extractor"].split(
        "_extractor="
    )[1]

    train_and_test_loop.main(wandb.config)


def main(config):
    config["sweep"]["general_settings"]["targets"] = [
        config["sweep"]["general_settings"]["target"]
    ]

    make_train_tune_split(config)
    wandb_sweep_config = make_wandb_sweep_config(config)

    sweep_id = wandb.sweep(wandb_sweep_config, project="wsi_classification")

    wandb.agent(sweep_id, evaluate_configuration)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Conduct a hyperparameter sweep based on the supplied configuration file."
    )
    parser.add_argument("--config", default="config/test.yaml")

    args = parser.parse_args()
    config = load_config(args.config)

    main(config)
