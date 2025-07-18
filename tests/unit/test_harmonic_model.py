import numpy as np
import pandas as pd
import pytest
import xarray as xr

import mesmer
from mesmer.core.utils import _check_dataarray_form
from mesmer.stats._harmonic_model import (
    _fit_fourier_order_np,
    _generate_fourier_series_np,
    predict_harmonic_model,
)
from mesmer.testing import trend_data_1D, trend_data_2D


def test_generate_fourier_series_np():
    # test if fourier series is generated correctly
    n_years = 10
    n_months = n_years * 12

    yearly_predictor = np.ones(n_months)
    months = np.tile(np.arange(12), n_years)
    alpha = 2 * np.pi * months / 12

    coeffs = np.array([0, -2, 0, -1])

    # dummy yearly cycle
    expected = coeffs[1] * np.cos(alpha) + coeffs[3] * np.sin(alpha)

    result = _generate_fourier_series_np(yearly_predictor, coeffs)

    np.testing.assert_allclose(result, expected, rtol=1e-13)

    coeffs = np.array([1, -2, 3.14, -1])
    result = _generate_fourier_series_np(yearly_predictor, coeffs)
    expected += 1 * np.cos(alpha) + 3.14 * np.sin(alpha)
    np.testing.assert_allclose(result, expected, atol=1e-10)


@pytest.mark.parametrize("stack", (True, False))
def test_predict_harmonic_model(stack):
    n_years = 10
    n_lat, n_lon, n_gridcells = 2, 3, 2 * 3
    time = xr.date_range(
        start="2000-01-01", periods=n_years, freq="YS", use_cftime=True
    )
    yearly_predictor = xr.DataArray(
        np.zeros((n_years, n_gridcells)), dims=["time", "cells"], coords={"time": time}
    )

    time = xr.date_range(
        start="2000-01-01", periods=n_years * 12, freq="MS", use_cftime=True
    )
    monthly_time = xr.DataArray(time, dims=["time"], coords={"time": time})

    coeffs = get_2D_coefficients(order_per_cell=[1, 2, 3], n_lat=n_lat, n_lon=n_lon)

    sample_dim = "sample" if stack else "time"
    if stack:
        yearly_predictor = yearly_predictor.stack(sample=["time"], create_index=False)
        monthly_time = monthly_time.stack(sample=["time"], create_index=False)

    result = mesmer.stats.predict_harmonic_model(
        yearly_predictor, coeffs, monthly_time, time_dim="time"
    )

    _check_dataarray_form(
        result,
        "result",
        ndim=2,
        required_dims={sample_dim, "cells"},
        required_coords="time",
        shape=(n_years * 12, n_gridcells),
    )


@pytest.mark.filterwarnings("ignore:divide by zero encountered in log")
@pytest.mark.parametrize(
    "coefficients",
    [
        np.array([0, -1, 0, -2]),
        np.array([1, 2, 3, 4, 5, 6, 7, 8]),
        np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]),
    ],
)
def test_fit_fourier_order_np(coefficients):
    # ensure original coeffs and series is recovered from noiseless fourier series
    max_order = 6
    n_years = 100
    yearly_predictor = trend_data_1D(n_timesteps=n_years, intercept=0, slope=1).values
    yearly_predictor = np.repeat(yearly_predictor, 12)
    monthly_target = _generate_fourier_series_np(yearly_predictor, coefficients)

    selected_order, estimated_coefficients, predictions = _fit_fourier_order_np(
        yearly_predictor, monthly_target, max_order=max_order
    )

    np.testing.assert_equal(selected_order, int(len(coefficients) / 4))

    # fill up all coefficient arrays with zeros to have the same length 4*max_order
    # to also be able to compare coefficients of higher orders than the original one
    original_coefficients = np.concatenate(
        [coefficients, np.zeros(4 * max_order - len(coefficients))]
    )
    estimated_coefficients = np.nan_to_num(
        estimated_coefficients,
        nan=0,
    )

    np.testing.assert_allclose(original_coefficients, estimated_coefficients, atol=1e-7)
    np.testing.assert_allclose(predictions, monthly_target, atol=1e-7)


def get_2D_coefficients(order_per_cell, n_lat=3, n_lon=2):
    n_cells = n_lat * n_lon
    max_order = 6

    # generate coefficients that resemble real ones
    # generate rapidly decreasing coefficients for increasing orders
    trend = np.repeat(np.linspace(1.2, 0.2, max_order) ** 2, 4)
    # the first coefficients are rather small  (scaling of seasonal variability with temperature change)
    # while the second ones are large (constant distance of each month from the yearly mean)
    scale = np.tile([0.01, 5.0], (n_cells, max_order * 2))
    # generate some variability so not all coefficients are exactly the same
    rng = np.random.default_rng(0)
    variability = rng.normal(loc=0, scale=0.1, size=(n_cells, max_order * 4))
    # put it together
    coeffs = trend * scale + variability
    coeffs = np.round(coeffs, 1)

    # replace superfluous orders with nans
    for cell, order in enumerate(order_per_cell):
        coeffs[cell, order * 4 :] = np.nan

    LON, LAT = np.meshgrid(np.arange(n_lon), np.arange(n_lat))

    coords = {
        "lon": ("cells", LON.flatten()),
        "lat": ("cells", LAT.flatten()),
    }

    return xr.DataArray(coeffs, dims=("cells", "coeff"), coords=coords)


def test_fit_harmonic_model():
    n_ts = 100
    orders = [1, 2, 3, 4, 5, 6]

    coefficients = get_2D_coefficients(order_per_cell=orders, n_lat=3, n_lon=2)

    yearly_predictor = trend_data_2D(n_timesteps=n_ts, n_lat=3, n_lon=2).transpose(
        "time", "cells"
    )

    yearly_predictor["time"] = xr.date_range(
        start="2000-01-01", periods=n_ts, freq="YS", use_cftime=True
    )

    time = xr.date_range(
        start="2000-01-01", periods=n_ts * 12, freq="MS", use_cftime=True
    )
    monthly_time = xr.DataArray(time, dims=["time"], coords={"time": time})

    monthly_target = predict_harmonic_model(
        yearly_predictor, coefficients, time=monthly_time
    )

    # test if the model can recover the monthly target from perfect fourier series
    result = mesmer.stats.fit_harmonic_model(yearly_predictor, monthly_target)
    np.testing.assert_equal(result.selected_order.values, orders)
    xr.testing.assert_allclose(
        result.residuals, xr.zeros_like(monthly_target), atol=1e-6
    )

    # test if the model can recover the underlying cycle with noise on top of monthly target
    rng = np.random.default_rng(0)
    noisy_monthly_target = monthly_target + rng.normal(
        loc=0, scale=0.1, size=monthly_target.shape
    )

    result = mesmer.stats.fit_harmonic_model(yearly_predictor, noisy_monthly_target)
    predictions = mesmer.stats.predict_harmonic_model(
        yearly_predictor, result.coeffs, time=monthly_time
    )
    xr.testing.assert_allclose(predictions, monthly_target, atol=0.1)

    # compare numerically one cell of one year
    expected = np.array(
        [
            0.014026,
            0.131156,
            -0.232648,
            0.040157,
            0.088749,
            -0.102724,
            -0.066836,
            0.133832,
            0.180308,
            -0.12783,
            -0.042045,
            0.160109,
        ]
    )

    result_comp = result.residuals.isel(cells=0, time=slice(0, 12)).values
    np.testing.assert_allclose(result_comp, expected, atol=1e-6)

    # ensure predictions and residuals are consistent
    expected = noisy_monthly_target - predictions

    xr.testing.assert_equal(expected, result.residuals)


def test_fit_harmonic_model_checks() -> None:
    yearly_predictor = trend_data_2D(n_timesteps=10, n_lat=3, n_lon=2)
    monthly_target = trend_data_2D(n_timesteps=10 * 12, n_lat=3, n_lon=2)

    with pytest.raises(TypeError):
        mesmer.stats.fit_harmonic_model(yearly_predictor.values, monthly_target)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        mesmer.stats.fit_harmonic_model(yearly_predictor, monthly_target.values)  # type: ignore[arg-type]

    yearly_predictor["time"] = pd.date_range("2000-01-01", periods=10, freq="YE")

    monthly_target["time"] = pd.date_range("2000-02-01", periods=10 * 12, freq="ME")
    with pytest.raises(ValueError, match="Monthly target data must start with January"):
        mesmer.stats.fit_harmonic_model(yearly_predictor, monthly_target)

    monthly_target["time"] = pd.date_range("2000-01-01", periods=10 * 12, freq="ME")

    with pytest.raises(ValueError, match="DataArray objects have different dimensions"):
        mesmer.stats.fit_harmonic_model(yearly_predictor.isel(cells=0), monthly_target)

    with pytest.raises(ValueError, match="DataArray objects have different dimensions"):
        mesmer.stats.fit_harmonic_model(
            yearly_predictor.rename(cells="gp"), monthly_target
        )

    with pytest.raises(ValueError, match="DataArray objects have different dimensions"):
        mesmer.stats.fit_harmonic_model(
            yearly_predictor, monthly_target.rename(cells="gp")
        )

    with pytest.raises(
        ValueError,
        match=r"The 'cells' coords of `yearly_predictor` and `monthly_target` have a different size: 6 vs. 4",
    ):
        mesmer.stats.fit_harmonic_model(
            yearly_predictor, monthly_target.isel(cells=slice(None, 4))
        )

    with pytest.raises(
        ValueError,
        match=r"The 'cells' coords of `yearly_predictor` and `monthly_target` have a different size: 5 vs. 6",
    ):
        mesmer.stats.fit_harmonic_model(
            yearly_predictor.isel(cells=slice(None, 5)), monthly_target
        )


def test_fit_harmonic_model_time_dim():
    # test if the time dimension can be different from "time"
    yearly_predictor = trend_data_2D(n_timesteps=10, n_lat=3, n_lon=2)
    monthly_target = trend_data_2D(n_timesteps=10 * 12, n_lat=3, n_lon=2)

    yearly_predictor["time"] = pd.date_range("2000-01-01", periods=10, freq="YE")

    monthly_target["time"] = pd.date_range("2000-01-01", periods=10 * 12, freq="ME")

    time_dim = "dates"
    monthly_target = monthly_target.rename({"time": time_dim})
    yearly_predictor = yearly_predictor.rename({"time": time_dim})
    res = mesmer.stats.fit_harmonic_model(
        yearly_predictor, monthly_target, time_dim=time_dim
    )

    _check_dataarray_form(res.selected_order, required_dims="cells")
    _check_dataarray_form(res.coeffs, required_dims={"cells", "coeff"})
    _check_dataarray_form(
        res.residuals, required_dims={"cells", "dates"}, required_coords="dates"
    )


def test_fit_harmonic_model_non_dim_coords():
    # test if the time dimension can be a non-dim coords
    yearly_predictor = trend_data_2D(n_timesteps=10, n_lat=3, n_lon=2)
    monthly_target = trend_data_2D(n_timesteps=10 * 12, n_lat=3, n_lon=2)

    yearly_predictor["time"] = pd.date_range("2000-01-01", periods=10, freq="YE")
    yearly_predictor = yearly_predictor.stack(sample=["time"], create_index=False)

    monthly_target["time"] = pd.date_range("2000-01-01", periods=10 * 12, freq="ME")
    monthly_target = monthly_target.stack(sample=["time"], create_index=False)

    res = mesmer.stats.fit_harmonic_model(yearly_predictor, monthly_target)

    _check_dataarray_form(res.selected_order, required_dims="cells")
    _check_dataarray_form(res.coeffs, required_dims={"cells", "coeff"})
    _check_dataarray_form(
        res.residuals, required_dims={"cells", "sample"}, required_coords="time"
    )
