from typing import Union, Dict, List, TYPE_CHECKING, Optional, Tuple
from pathlib import Path
import logging

import numpy as np
from dgl.dataloading import GraphDataLoader
from lightning.pytorch import Trainer
from lightning.pytorch.loggers import Logger
import torch
from torch import nn
import lightning.pytorch as pl

from ..dgl.gnn_architectures.gat import GAT
from ..dgl.gnn_architectures.resettable_module import ResettableModule
from ..lightning.node_regression_module import NodeRegressionModule
from ..lightning.console_logger import ConsoleLogger
from ..data.abstract_masked_dataset import AbstractMaskedDataset


class GnnPredictor:
    def __init__(
        self,
        mapping: str = "gene",
        value_columns: Union[Dict[str, List[str]], List[str]] = ["abundance"],
        molecule_columns: List[str] = [],
        target_column: str = "abundance",
        module: Optional[pl.LightningModule] = None,
        model: ResettableModule = GAT(in_dim=4, hidden_dim=40, out_dim=1, num_heads=20),
        missing_substitute_value: float = 00,
        bidirectional_graph: bool = True,
        logger: Logger = ConsoleLogger(),  # type: ignore
    ):
        self.mapping = mapping
        self.value_columns = value_columns
        self.molecule_columns = molecule_columns
        self.target_column = target_column
        self.model = model
        self.missing_substitute_value = missing_substitute_value
        self.bidirectional_graph = bidirectional_graph
        self.module = module
        if self.module is None:
            if model is None:
                raise AttributeError("Please either specify a model or a lightning module!")
            self.module = NodeRegressionModule(
                model=self.model,
                nan_substitute_value=missing_substitute_value,
                mask_substitute_value=missing_substitute_value,
                hide_substitute_value=missing_substitute_value,
            )
        self.logger = logger

    def fit(
        self,
        train_mds: AbstractMaskedDataset,
        test_mds: Optional[AbstractMaskedDataset],
        max_epochs: int = 10,
        reset_parameters: bool = False,
        silent: bool = False,
        check_val_every_n_epoch: int = 1,
    ):
        if reset_parameters:
            self.reset_parameters()
        train_gds = train_mds.get_graph_dataset_dgl(
            mapping=self.mapping,
            value_columns=self.value_columns,
            molecule_columns=self.molecule_columns,
            target_column=self.target_column,
            missing_column_value=self.missing_substitute_value,
        )
        train_dl = GraphDataLoader(train_gds, batch_size=1)  # TODO: think about batch size
        val_dl = None
        if test_mds is not None:
            test_gds = test_mds.get_graph_dataset_dgl(
                mapping=self.mapping,
                value_columns=self.value_columns,
                molecule_columns=self.molecule_columns,
                target_column=self.target_column,
                missing_column_value=self.missing_substitute_value,
            )
            val_dl = GraphDataLoader(test_gds, batch_size=1)
        #ptl_logger = logging.getLogger("lightning.pytorch")
        #plt_log_level = ptl_logger.level
        #if silent:
        #    ptl_logger.setLevel(logging.ERROR)
        trainer = Trainer(
            logger=self.logger,
            max_epochs=max_epochs,
            enable_checkpointing=False,
            enable_progress_bar=not silent,
            enable_model_summary=not silent,
            check_val_every_n_epoch=check_val_every_n_epoch,
        )
        trainer.fit(self.module, train_dataloaders=train_dl, val_dataloaders=val_dl)
        #if silent:
        #    ptl_logger.setLevel(plt_log_level)

    def predict(
        self,
        mds: AbstractMaskedDataset,
        result_column: Optional[Union[str, Tuple[str]]] = None,
        copy_non_predicted_from_target_column: bool = True,
        silent: bool = False,
    ):
        if result_column is None:
            result_column = self.target_column
        if not isinstance(result_column, (list, tuple)):
            result_column = [result_column]
        if self.module.out_dim != len(result_column):
            raise AttributeError(
                f"The prediction module has {self.module.out_dim} output dimensions but {len(result_column)} result column names were given!"
            )
        # graph = sample.molecule_set.create_graph(mapping=mapping).to_dgl()
        # sample.populate_graph_dgl(graph, value_columns=value_columns, mapping=mapping)
        graph_ds = mds.get_graph_dataset_dgl(
            mapping=self.mapping,
            value_columns=self.value_columns,
            molecule_columns=self.molecule_columns,
            target_column=self.target_column,
            missing_column_value=self.missing_substitute_value,
        )
        # we only have one dataset/graph so we only need to compute the node mapping once
        graph = graph_ds.graph
        dl = GraphDataLoader(graph_ds, batch_size=1)
        with torch.no_grad():
            #ptl_logger = logging.getLogger("lightning.pytorch")
            #plt_log_level = ptl_logger.level
            #if silent:
            #   ptl_logger.setLevel(logging.ERROR)
            trainer = Trainer(enable_progress_bar=not silent, enable_model_summary=not silent)
            predictions = trainer.predict(self.module, dl)
            #if silent:
            #    ptl_logger.setLevel(plt_log_level)
            for i, prediction in enumerate(predictions):
                batch = graph_ds[i]
                mask_nodes = batch.ndata["mask"].detach().squeeze().numpy()
                assert np.all(graph.nodes.iloc[mask_nodes].type == graph.type_mapping[mds.molecule])
                prediction = prediction[mask_nodes]
                sample = graph_ds.index_to_sample(i)
                if copy_non_predicted_from_target_column:
                    # TODO
                    sample.values[mds.molecule].loc[:, result_column[0]] = sample.values[mds.molecule].loc[
                        :, self.target_column
                    ]
                else:
                    sample.values[mds.molecule].loc[:, result_column] = sample.dataset.missing_value
                molecules = graph.nodes.loc[mask_nodes.nonzero(), "molecule_id"].values  # type: ignore
                prediction = prediction.detach().numpy()
                for i, c in enumerate(result_column):
                    sample.values[mds.molecule].loc[molecules, c] = prediction[:, i]

    @property
    def out_dim(self):
        return self.model.out_dim

    def reset_parameters(self):
        self.model.reset_parameters()

    def save_model(self, path: Union[str, Path]):
        path = Path(path)
        torch.save(
            {
                "model_state_dict": self.model.state_dict(),
            },
            path,
        )

    def load_model(self, path: Union[str, Path]):
        path = Path(path)
        checkpoint = torch.load(path)
        self.model.load_state_dict(checkpoint["model_state_dict"])
