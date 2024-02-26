import argparse
import source.tessalate.preprocessor as preprocessor
from source.utils.utils import load_general_config, load_specific_config
from tqdm import tqdm
from collections import defaultdict


def main(config):
    # Format requested patch sizes and corresponding magnification levels in a dict
    patch_sizes_vs_magnification_levels = defaultdict(set)
    for model, settings in config["extractor_models"].items():
        patch_sizes_vs_magnification_levels[tuple(settings["patch_dimensions"])].update(
            settings["extraction_levels"]
        )

    # Loop through all requested patch sizes
    for patch_dimensions, magnification_levels in tqdm(
        patch_sizes_vs_magnification_levels.items(),
        desc="Extracting at different patch sizes",
        unit="sizes",
        leave=False,
    ):
        config["patch_dimensions"] = list(patch_dimensions)

        # Loop through all requested levels for this patch size
        for level in tqdm(
            magnification_levels,
            desc="Extracting at different magnification levels",
            unit="levels",
            leave=False,
        ):
            config["extraction_level"] = level

            # Extract patches
            preprocessor.main(config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tessalate slides at all requested levels and patch sizes"
    )
    parser.add_argument("--config", default="config/general/umcu.yaml")
    args = parser.parse_args()

    general_config = load_general_config(args.config)
    specific_config = load_specific_config(args.config, "tessalate")

    config = general_config | specific_config

    main(config)