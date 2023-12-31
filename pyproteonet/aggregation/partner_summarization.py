from typing import Union, Callable, Optional

import numpy as np
import pandas as pd
from pandas.core.groupby.generic import SeriesGroupBy

from ..utils.numpy import eq_nan
from ..data.dataset import Dataset

def _get_mapped(
    dataset: Dataset,
    molecule: str,
    mapping: str,
    partner_column: str,
    only_unique: bool = True,
)->pd.DataFrame:
    molecule, mapping, partner_molecule = dataset.infer_mapping(molecule=molecule, mapping=mapping)
    mapped = dataset.get_mapped(molecule=molecule, partner_columns=[partner_column], mapping=mapping)
    mapped.rename(columns={partner_column:'quanti'}, inplace=True)
    degs = dataset.molecule_set.get_mapping_degrees(molecule=partner_molecule, mapping=mapping)
    mapped['deg'] = degs.loc[mapped.index.get_level_values(level=partner_molecule)].values
    mapped = mapped[~eq_nan(mapped.quanti, dataset.missing_value)]
    if only_unique:
        mapped = mapped[mapped.deg==1]
    return mapped

def partner_aggregation(
    dataset: Dataset,
    molecule: str,
    partner_column: str,
    mapping: str,
    method: Union[Callable[[SeriesGroupBy], pd.Series], str] = 'sum',
    only_unique: bool = True,
    result_column: Optional[str] = None,
    is_log: bool = False,
) -> pd.Series:
    if isinstance(method, str):
        method = method.lower()
        if method == 'mean':
            ag_fn = lambda group: group.mean()
        if method == 'sum':
            ag_fn = lambda group: group.sum()
        elif method == 'median':
            ag_fn = lambda group: group.median()
        elif method == 'min':
            ag_fn = lambda group: group.min()
        elif method == 'max':
            ag_fn = lambda group: group.max()
        else:
            raise AttributeError(f"Aggregation function {method} not known.")
    else:
        ag_fn = method
    mapped = _get_mapped(dataset=dataset, molecule=molecule, mapping=mapping, partner_column=partner_column, only_unique=only_unique)
    if is_log:
        mapped['quanti'] = np.exp(mapped['quanti'])
    group = mapped.quanti.groupby(['sample', molecule])
    res = ag_fn(group)
    res.index.set_names('id', level=1, inplace=True)
    if is_log:
        res = np.log(res)
    if result_column is not None:
        dataset.values[molecule][result_column] = res
    return res

def partner_top_n_mean(
    dataset: Dataset,
    molecule: str,
    mapping: str,
    partner_column: str,
    top_n: int = 3,
    only_unique: bool = True,
    result_column: Optional[str] = None,
    skip_if_less_than_n: bool = True,
    is_log: bool = False,
)->Optional[pd.Series]:
    mapped = _get_mapped(dataset=dataset, molecule=molecule, mapping=mapping, partner_column=partner_column, only_unique=only_unique)
    if is_log:
        mapped['quanti'] = np.exp(mapped['quanti'])
    group = mapped.quanti.sort_values(ascending=False).groupby(['sample', molecule]).head(top_n).groupby(['sample',molecule])
    if skip_if_less_than_n:
        res = group.mean()[group.count() >= top_n]
    else:
        res = group.mean()
    res.index.set_names('id', level=1, inplace=True)
    if is_log:
        res = np.log(res)
    if result_column is not None:
        dataset.set_column_flat(molecule=molecule, values=res, column=result_column, fill_missing=True)
    return res