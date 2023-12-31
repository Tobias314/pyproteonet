from typing import Optional, Union
import math

import numpy as np
import pandas as pd
from fancyimpute import IterativeSVD, Solver

from ..utils.numpy import eq_nan
from ..data.dataset import Dataset


def generic_fancy_impute(
    dataset: Dataset,
    molecule: str,
    column: str,
    imputer: Solver,
    result_column: Optional[str] = None,
    inplace: bool = False,
    **kwargs
) -> Dataset:
    if not inplace:
        dataset = dataset.copy()
    if result_column is None:
        result_column = column
    matrix = dataset.get_samples_value_matrix(molecule=molecule, column=column)
    matrix_vals = matrix.values
    missing_mask = eq_nan(matrix_vals, dataset.missing_value)
    matrix_vals[missing_mask] = 0
    matrix_imputed = imputer.solve(matrix_vals, missing_mask=missing_mask)
    print(matrix_imputed.mean())
    matrix_imputed = pd.DataFrame(matrix_imputed, columns=matrix.columns, index=matrix.index)
    vals = matrix_imputed.stack().swaplevel()
    vals.index.set_names(["sample", "id"], inplace=True)
    return vals


def iterative_svd_impute(
    dataset: Dataset,
    molecule: str,
    column: str,
    result_column: Optional[str] = None,
    inplace: bool = False,
    min_value: Optional[float] = None,
    rank: Union[float, int] = 0.2,
    **kwargs
) -> Dataset:
    if min_value is None:
        min_value = dataset.values[molecule][column].min()
    if rank == -1:
        rank = len(dataset.sample_names) - 1
    if 0 < rank < 1.0:
        rank = min(math.ceil(len(dataset.sample_names) * 0.2), len(dataset.sample_names) - 1)
    imputer = IterativeSVD(min_value=min_value, rank=rank, **kwargs)
    res = generic_fancy_impute(
        dataset=dataset, molecule=molecule, column=column, imputer=imputer, result_column=result_column, inplace=inplace
    )
    return res
