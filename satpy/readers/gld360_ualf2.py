#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 Satpy developers
#
# This file is part of satpy.
#
# satpy is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# satpy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# satpy.  If not, see <http://www.gnu.org/licenses/>.

"""Vaisala Global Lightning Dataset 360 reader for Universal ASCII Lightning Format 2 (UALF2).

Vaisala Global Lightning Dataset GLD360 is data as a service
that provides real-time lightning data for accurate and early
detection and tracking of severe weather. The data provided is
generated by a Vaisala owned and operated world-wide lightning
detection sensor network.

References:
- [GLD360] https://www.vaisala.com/en/products/data-subscriptions-and-reports/data-sets/gld360
- [SMHI] https://opendata.smhi.se/apidocs/lightning/parameters.html

"""

import logging
from datetime import timedelta

import dask.dataframe as dd
import numpy as np
import xarray as xr

from satpy.readers.file_handlers import BaseFileHandler

logger = logging.getLogger(__name__)

UALF2_DTYPES = {
    "ualf_record_type": np.uint8,
    "network_type": np.uint8,
    "year": str,
    "month": str,
    "day": str,
    "hour": str,
    "minute": str,
    "second": str,
    "latitude": np.float32,
    "longitude": np.float32,
    "altitude": np.uint16,
    "altitude_uncertainty": np.uint16,
    "peak_current": np.int16,
    "vhf_range": np.float32,
    "multiplicity_flash": np.uint8,
    "cloud_pulse_count": np.int16,
    "number_of_sensors": np.uint8,
    "degree_freedom_for_location": np.uint8,
    "error_ellipse_angle": np.float32,
    "error_ellipse_max_axis_length": np.float32,
    "error_ellipse_min_axis_length": np.float32,
    "chi_squared_value_location_optimization": np.float32,
    "wave_form_rise_time": np.float32,
    "wave_form_peak_to_zero_time": np.float32,
    "wave_form_max_rate_of_rise": np.float32,
    "cloud_indicator": bool,
    "angle_indicator": bool,
    "signal_indicator": bool,
    "timing_indicator": bool,
}


def _create_column_names():
    """Insert nanoseconds in the column names to a correct index."""
    tmp = [*UALF2_DTYPES]
    idx = tmp.index("second") + 1
    tmp.insert(idx, "nanosecond")

    return tmp


UALF2_COLUMN_NAMES = _create_column_names()


class VaisalaGld360Ualf2FileHandler(BaseFileHandler):
    """FileHandler for Vaisala GLD360 data in UALF2-format."""

    def __init__(self, filename, filename_info, filetype_info):
        """Initialize FileHandler."""
        super(VaisalaGld360Ualf2FileHandler, self).__init__(filename, filename_info, filetype_info)

        self.data = dd.read_csv(filename,
                                sep="\t",
                                header=None,
                                names=UALF2_COLUMN_NAMES,
                                dtype=UALF2_DTYPES,
                                converters={"nanosecond": self.pad_nanoseconds}
                                )

        combined_time = (self.data["year"] + " " +
                         self.data["month"] + " " +
                         self.data["day"] + " " +
                         self.data["hour"] + " " +
                         self.data["minute"] + " " +
                         self.data["second"] + " " +
                         self.data["nanosecond"])

        self.data["time"] = dd.to_datetime(combined_time, format="%Y %m %d %H %M %S %f")
        self.data = self.data.drop_duplicates()
        self.data = self.data.sort_values("time")

    @property
    def start_time(self):
        """Return start time."""
        return self.filename_info["start_time"]

    @property
    def end_time(self):
        """Return end time."""
        return self.filename_info["start_time"] + timedelta(hours=1)

    def get_dataset(self, dataset_id, dataset_info):
        """Return the dataset."""
        # create xarray and place along y dimension
        data_array = xr.DataArray(self.data[dataset_id["name"]].to_dask_array(lengths=True), dims=["y"])
        # assign dataset infos to xarray attrs
        data_array.attrs.update(dataset_info)
        return data_array

    @staticmethod
    def pad_nanoseconds(nanoseconds):
        """Read ns values for less than 0.1s correctly (these are not zero-padded in the input files)."""
        return str(nanoseconds).zfill(9)