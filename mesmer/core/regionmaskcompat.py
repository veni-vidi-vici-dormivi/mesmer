# code vendored from regionmask under the conditions of their license
# see licenses/REGIONMASK_LICENSE

import warnings

import numpy as np
import regionmask
import xarray as xr
from packaging.version import Version

if Version(regionmask.__version__) >= Version("0.12.0"):

    from regionmask.core.mask import (
        InvalidCoordsError,  # pyright: ignore[reportAssignmentType]
    )
else:

    class InvalidCoordsError(ValueError):  # type: ignore[no-redef]
        pass


def mask_3D_frac_approx(
    regions: regionmask.Regions, lon, lat, **kwargs
) -> xr.DataArray:
    """3D mask of the fractional overlap of a set of regions for the given lat/ lon grid

    Parameters
    ----------
    regions : regionmask.Regions
        Region definitions.
    lon : array
        Array of longitude coordinates.
    lat : array
        Array of latitude coordinates.
    **kwargs : keyword arguments
        Passed to regions.mask

    Returns
    -------
    mask_3D : boolean xarray.DataArray
        3D mask with fractional overlap

    Notes
    -----
    - assumes equally-spaced lat & lon!
    - copied from Mathias Hauser: https://github.com/regionmask/regionmask/issues/38 in
      August 2020
    - prototype of what will eventually be integrated in his regionmask package

    """

    warnings.warn(
        "`mask_3D_frac_approx` has been deprecated. Please use "
        "`regions.mask_3D_frac_approx` directly (requires regionmask v0.12 or later).",
        FutureWarning,
    )

    return _mask_3D_frac_approx(regions, lon, lat, **kwargs)


def _mask_3D_frac_approx(regions, lon, lat, **kwargs):

    if Version(regionmask.__version__) >= Version("0.12.0"):

        # TODO: use this function directly once requiring regionmask >= 0.12
        return regions.mask_3D_frac_approx(lon, lat, **kwargs)
    else:
        return _mask_3D_frac_approx_internal(regions, lon, lat, **kwargs)


def _mask_3D_frac_approx_internal(
    regions: regionmask.Regions, lon, lat, **kwargs
) -> xr.DataArray:

    backend = regionmask.core.mask._determine_method(
        lon, lat
    )  # pyright: ignore[reportAttributeAccessIssue]
    if "rasterize" not in backend:
        raise InvalidCoordsError("'lon' and 'lat' must be 1D and equally spaced.")

    if np.min(lat) < -90 or np.max(lat) > 90:
        raise InvalidCoordsError("lat must be between -90 and +90")

    lon_name = getattr(lon, "name", "lon")
    lat_name = getattr(lat, "name", "lat")

    lon_sampled = sample_coord(lon)
    lat_sampled = sample_coord(lat)

    ds = xr.Dataset(coords={lon_name: lon_sampled, lat_name: lat_sampled})

    mask = regions.mask(ds[lon_name], ds[lat_name], **kwargs)

    sel = (mask[lat_name] >= -90) & (mask[lat_name] <= 90)

    isnan = np.isnan(mask.values)

    numbers = np.unique(mask.values[~isnan])
    numbers = numbers.astype(int)

    res: list[xr.DataArray] = list()
    for num in numbers:
        # coarsen the mask again
        mask_coarse = mask == num
        # set points beyond 90° to NaN so we get the correct fraction
        mask_coarse = mask_coarse.where(sel)
        mask_coarse = mask_coarse.coarsen({lat_name: 10, lon_name: 10}).mean()
        res.append(mask_coarse)

    mask_sampled = xr.concat(res, dim="region", compat="override", coords="minimal")

    abbrevs = regions[numbers].abbrevs
    names = regions[numbers].names

    coords = {
        "region": numbers,
        lon_name: lon,
        lat_name: lat,
        "abbrevs": ("region", abbrevs),
        "names": ("region", names),
    }
    mask_sampled = mask_sampled.assign_coords(coords)

    return mask_sampled


def sample_coord(coord):
    """Sample coords for the percentage overlap.

    Notes
    -----
    - copied from Mathias Hauser: https://github.com/regionmask/regionmask/issues/38
      in August 2020
    -> prototype of what will eventually be integrated in his regionmask package

    """

    coord = np.asarray(coord)

    d_coord = coord[1] - coord[0]

    n_cells = coord.size

    left = coord[0] - d_coord / 2 + d_coord / 20
    right = coord[-1] + d_coord / 2 - d_coord / 20

    return np.linspace(left, right, n_cells * 10)
