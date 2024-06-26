import os
import torch
import pandas as pd
import pytorch_lightning as pl
import multiprocessing as mp
from torch.utils.data import DataLoader, Dataset
from source.utils.utils import (
    get_features_dir_name,
    get_cross_val_splits_dir_path,
    get_patch_coordinates_dir_name,
)


class PreextractedFeatureDataset(Dataset):
    def __init__(self, manifest_path: os.PathLike, config: dict) -> None:
        manifest = pd.read_csv(manifest_path)
        self.config = config

        self.targets = config["targets"]

        self.data = manifest[["slide_id"] + self.targets].dropna()

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, ix: int) -> "tuple[torch.Tensor, torch.Tensor, str]":
        case = self.data.iloc[ix]

        patch_coordinates_dir = get_patch_coordinates_dir_name(self.config)
        patch_coordinates_path = patch_coordinates_dir / (case["slide_id"] + ".csv")
        patch_coordinates = pd.read_csv(patch_coordinates_path)
        patches_to_use_given_segmentation = patch_coordinates[
            self.config["segmentation"]
        ]

        features_dir = get_features_dir_name(self.config)
        features_path = str(features_dir / (case["slide_id"] + ".pt"))

        x = torch.load(features_path).float()[patches_to_use_given_segmentation]
        y = torch.tensor(case[self.targets]).float()

        return x, y, features_path


class ClassificationDataModule(pl.LightningDataModule):
    def __init__(self, config: dict) -> None:
        super().__init__()
        self.cross_val_splits_directory = (
            get_cross_val_splits_dir_path(config) / f"fold_{config['fold']}"
        )
        self.config = config

    def setup(self, stage: str = "fit") -> None:
        if stage == "fit":
            self.train_dataset = PreextractedFeatureDataset(
                self.cross_val_splits_directory / "train.csv", self.config
            )
            self.val_dataset = PreextractedFeatureDataset(
                self.cross_val_splits_directory / "tune.csv", self.config
            )

        if stage == "test":
            self.test_dataset = PreextractedFeatureDataset(
                self.cross_val_splits_directory / "test.csv", self.config
            )

    def train_dataloader(self) -> DataLoader:
        return DataLoader(
            self.train_dataset,
            batch_size=1,
            shuffle=True,
            num_workers=self.config["num_workers"],
        )

    def val_dataloader(self) -> DataLoader:
        return DataLoader(
            self.val_dataset,
            batch_size=1,
            shuffle=False,
            num_workers=self.config["num_workers"],
        )

    def test_dataloader(self) -> DataLoader:
        return DataLoader(
            self.test_dataset,
            batch_size=1,
            shuffle=False,
            num_workers=(
                self.config["num_workers"]
                if self.config["num_workers"] is not None
                else mp.cpu_count()
            ),
        )
