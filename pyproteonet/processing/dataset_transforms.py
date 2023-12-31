from typing import Union, Dict, Callable, Optional, List, TYPE_CHECKING, Iterable

import numpy as np
import pandas as pd

from ..utils.numpy import eq_nan

if TYPE_CHECKING:
    from ..data.dataset import Dataset
    from ..data.dataset_sample import DatasetSample


def apply(data: Union["DatasetSample", "Dataset"], dataset_fn: Callable, *args, **kwargs):
    return data.sample_apply(dataset_fn, *args, **kwargs)


def _normalize(ds: "DatasetSample", molecules: Optional[Iterable[str]] = None, columns: Optional[List[str]] = None):
    ds = ds.copy()
    if molecules is None:
        molecules = ds.values.keys()
    for molecule in molecules:
        df = ds.values[molecule]
        cs = columns
        if cs is None:
            cs = list(df.keys())
        for column in cs:
            df.loc[:, column] = (df.loc[:, column] - df.loc[:, column].mean()) / df.loc[:, column].std()
    return ds


def normalize(
    data: Union["DatasetSample", "Dataset"],
    molecules: Optional[Iterable[str]] = None,
    columns: Optional[Iterable[str]] = None,
):
    return data.sample_apply(_normalize, molecules=molecules, columns=columns)


def _logarithmize(
    ds: "DatasetSample",
    molecules: Optional[Iterable[str]] = None,
    columns: Optional[Iterable[str]] = None,
    epsilon: float = 0.0,
):
    ds = ds.copy()
    if molecules is None:
        molecules = ds.values.keys()
    for molecule in molecules:
        df = ds.values[molecule]
        cs = columns
        if cs is None:
            cs = list(df.keys())
        for column in cs:
            if column not in df.keys():
                continue
            mask = ~ds.missing_mask(molecule=molecule, column=column)
            res = np.log(df.loc[mask, column] + epsilon)
            if np.isnan(res).any():
                raise ValueError("Log resutled in NaN values!")
            df.loc[mask, column] = res
    return ds


def logarithmize(
    data: Union["DatasetSample", "Dataset"],
    molecules: Optional[Iterable[str]] = None,
    columns: Optional[Iterable[str]] = None,
    epsilon: float = 0.0,
):
    return apply(data, _logarithmize, molecules=molecules, columns=columns, epsilon=epsilon)


def _rename_values(
    sample: "DatasetSample", columns: Dict[str, str], molecules: Optional[Iterable[str]] = None, inplace: bool = False
):
    if not inplace:
        sample = sample.copy()
    if molecules is None:
        molecules = list(sample.values.keys())
    for mol in molecules:
        sample.values[mol].rename(columns=columns, inplace=True)
    return sample


def rename_values(
    data: Union["DatasetSample", "Dataset"],
    columns: Dict[str, str],
    molecules: Optional[Iterable[str]] = None,
    inplace: bool = False,
):
    res = apply(data, _rename_values, columns=columns, molecules=molecules, inplace=inplace)
    if not inplace:
        return res

def _rename_columns(
    sample: "DatasetSample", columns: Dict[str, Dict[str, str]], inplace: bool = False
):
    if not inplace:
        sample = sample.copy()
    for mol, cols in columns.items():
        sample.values[mol].rename(columns=cols, inplace=True)
    return sample


def rename_columns(
    dataset: Union["DatasetSample", "Dataset"],
    columns: Dict[str, Dict[str, str]],
    inplace: bool = False,
):
    res = apply(dataset, _rename_columns, columns=columns,inplace=inplace)
    if not inplace:
        return res


def _drop_values(
    sample: "DatasetSample", columns: List[str], molecules: Optional[Iterable[str]] = None, inplace: bool = False
):
    if not inplace:
        sample = sample.copy()
    if molecules is None:
        molecules = list(sample.values.keys())
    for mol in molecules:
        sample.values[mol].drop(columns=columns, inplace=True)
    return sample


def drop_values(
    data: Union["DatasetSample", "Dataset"],
    columns: Iterable[str],
    molecules: Optional[Iterable[str]] = None,
    inplace: bool = False,
):
    res = apply(data, _drop_values, columns=columns, molecules=molecules, inplace=inplace)
    if not inplace:
        return res
