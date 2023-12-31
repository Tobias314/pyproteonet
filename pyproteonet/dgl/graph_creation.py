import itertools
from typing import List, Tuple, Dict, Optional, TYPE_CHECKING, Iterable, Union
import logging

import pandas as pd
import numpy as np
import dgl
import torch

if TYPE_CHECKING:
    from ..data.molecule_set import MoleculeSet
    from ..data.dataset_sample import DatasetSample
    from ..data.molecule_graph import MoleculeGraph

logger = logging.Logger("graph_creation")


def create_graph_dgl(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    external_edges: Optional[pd.DataFrame] = None,
    edge_name: str = "interacts",
    add_self_loops: bool = False,
) -> dgl.DGLGraph:
    if external_edges != None:
        raise NotImplemented("External edges are not supported in this method yet")
    graph_data = {
        ("molecule", edge_name, "molecule"): (edges.source_node, edges.destination_node),
    }
    # ('molecule', 'external', 'molecule'): ([], [])}
    dgl_N = dgl.heterograph(graph_data, num_nodes_dict={"molecule": nodes.shape[0]})  # type: ignore
    # dgl_N = dgl.graph(data = (edges.source_node, edges.destination_node), num_nodes = nodes.shape[0])
    if "weight" in edges.columns:
        dgl_N.edges[edge_name].data["w"] = torch.tensor(edges.weight.to_numpy().astype(np.float32))
    else:
        dgl_N.edges[edge_name].data["w"] = torch.ones((edges.shape[0],), dtype=torch.float32)
    if add_self_loops:
        dgl_N = dgl.add_self_loop(dgl_N, etype=edge_name)
    return dgl_N


def populate_graph_dgl(
    graph: "MoleculeGraph",
    dgl_graph: dgl.DGLGraph,
    dataset_sample: "DatasetSample",
    feature_columns: Union[Dict[str, List[str]], List[str]] = [],
    molecule_columns: List[str] = [],
    target_column: str = "abundance",
    missing_column_value: Optional[float] = None,
):
    if not (isinstance(feature_columns, list) or isinstance(feature_columns, dict)):
        raise ValueError(
            "value_columns must either be list of strings representing the colums present "
            + "for any molecule to use as graph features or a dict mapping from molecule type name"
            + "to list of stings representing the value columns to use for every molecule type."
        )
    if isinstance(feature_columns, list):
        node_type_groups = [(node_type, df) for node_type, df in graph.nodes.groupby("type")]
        feature_columns = {graph.inverse_type_mapping[node_type]: feature_columns for node_type, _ in node_type_groups}  # type: ignore
    all_value_columns = []
    for vcs in feature_columns.values():
        all_value_columns.extend(vcs)
    num_value_columns = max([len(columns) for _, columns in feature_columns.items()])
    node_molecule_values = dataset_sample.molecule_set.get_node_values_for_graph(graph=graph, include_id_and_type=False, columns=molecule_columns)
    num_nodes = dgl_graph.num_nodes("molecule")
    num_columns = num_value_columns + len(molecule_columns)
    x = np.full((num_nodes, num_columns), dataset_sample.missing_value, dtype=np.float32)
    target = np.full((num_nodes, 1), dataset_sample.missing_value, dtype=np.float32)
    if target_column not in all_value_columns:
        target_not_in_values = True
        #value_columns = {mol:cols + [target_column] for mol,cols in value_columns.items()}
    else:
        raise ValueError("The target column should not be part of the feature columns")
        target_not_in_values = False
    for molecule, columns in feature_columns.items():
        nodes = graph.node_mapping[molecule].loc[dataset_sample.values[molecule].index, "node_id"]
        for i, column in enumerate(columns):
            values = dataset_sample.values[molecule]
            if column in values.columns:
                values = values.loc[:, column].to_numpy().astype(np.float32)
            else:
                if missing_column_value is not None:
                    logger.info(
                        f"Column {column} is missing for molecule {molecule}, creating a column full of {missing_column_value}s instead!"
                    )
                    values = pd.Series(missing_column_value, index=dataset_sample.molecules[molecule].index)
                else:
                    raise (
                        KeyError(
                            f"Column {column} does not exist for molecule {molecule}!"
                            + "If you would like use a constant value for values of missing columns"
                            + " please set the missing_column_value arguement."
                        )
                    )
            # if column == target_column:
            #     target[nodes, 0] = values
            #     if target_not_in_values:
            #         continue
            x[nodes, i] = values
        target[nodes, 0] = dataset_sample.values[molecule].loc[:, target_column].to_numpy().astype(np.float32)
    for i, column in enumerate(molecule_columns):
        i = i + num_value_columns
        values = node_molecule_values[column].to_numpy().astype(np.float32)
        x[node_molecule_values.index, i] = values
        i += 1
    nodes_data = graph.nodes.loc[:, "type"]  # type: ignore
    # nodes_data[node_values.columns] = node_values
    node_molecule_labels = np.zeros((nodes_data.shape[0], int(nodes_data.max() + 1)), dtype=np.float32)
    node_molecule_labels[nodes_data.index.to_numpy(), nodes_data.to_numpy()] = 1
    # dgl_N = dgl.to_bidirected(dgl_N)
    dgl_graph.nodes["molecule"].data["features"] = torch.from_numpy(np.append(x, node_molecule_labels, axis=1))
    dgl_graph.nodes["molecule"].data["target"] = torch.from_numpy(target)
    # for i, column in enumerate(value_columns):
    #    dgl_graph.nodes['molecule'].data[column] = torch.from_numpy(x[:, i]).unsqueeze(axis=1)
    dgl_graph.nodes["molecule"].data["type"] = torch.from_numpy(node_molecule_labels)

    # dgl_N.edges['external'].data['w'] = torch.tensor(edge_weights_external.tolist())
    # dgl_graph = dgl.add_self_loop(dgl_graph, etype = 'external')

    # dgl.save_graphs(save_sample_name, dgl_N)
    logger.info("node abundances", x.shape)
    logger.info("number of nodes DGL", dgl_graph.num_nodes())
    logger.info("number of edges DGL", dgl_graph.num_edges())
    # print('Node Data', dgl_N.ndata['x'])
    # print('Edge Data', dgl_N.edata['w'])
