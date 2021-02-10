#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2021 Satpy developers
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
"""Functions and utilities for downloading ancillary data."""

import os
import logging
import satpy

import pooch

logger = logging.getLogger(__name__)

_FILE_REGISTRY = {}
_FILE_URLS = {}


def register_file(url, filename, component_type=None, known_hash=None):
    """Register file for future retrieval.

    This function only prepares Satpy to be able to download and cache the
    provided file. It will not download the file. See
    :func:`satpy.data_download.retrieve` for more information.

    Args:
        url (str): URL where remote file can be downloaded.
        filename (str): Filename used to identify and store the downloaded
            file as.
        component_type (str or None): Name of the type of Satpy component that
            will use this file. Typically "readers", "composites", "writers",
            or "enhancements" for consistency. This will be prepended to the
            filename when storing the data in the cache.
        known_hash (str): Hash used to verify the file is downloaded correctly.
            See https://www.fatiando.org/pooch/v1.3.0/beginner.html#hashes
            for more information. If not provided then the file is not checked.

    Returns:
        Cache key that can be used to retrieve the file later. The cache key
        consists of the ``component_type`` and provided ``filename``. This
        should be passed to :func:`satpy.data_download_retrieve` when the
        file will be used.

    """
    fname = _generate_filename(filename, component_type)

    global _FILE_REGISTRY
    global _FILE_URLS
    _FILE_REGISTRY[fname] = known_hash
    _FILE_URLS[fname] = url
    return fname


def _generate_filename(filename, component_type):
    if filename is None:
        return None
    path = filename
    if component_type:
        path = '/'.join([component_type, path])
    return path


def retrieve(cache_key, pooch_kwargs=None):
    """Download and cache the file associated with the provided ``cache_key``.

    Cache location is controlled by the config ``data_dir`` key. See
    :ref:`data_dir_setting` for more information.

    Args:
        cache_key (str): Cache key returned by
            :func:`~satpy.data_download.register_file`.
        pooch_kwargs (dict or None): Extra keyword arguments to pass to
            :meth:`pooch.Pooch.fetch`.

    Returns:
        Local path of the cached file.


    """
    pooch_kwargs = pooch_kwargs or {}

    path = satpy.config.get('data_dir')
    # reuse data directory as the default URL where files can be downloaded from
    pooch_obj = pooch.create(path, path, registry=_FILE_REGISTRY,
                             urls=_FILE_URLS)
    return pooch_obj.fetch(cache_key, **pooch_kwargs)


def retrieve_all(pooch_kwargs=None):
    """Find cache-able data files for Satpy and download them.

    The typical use case for this function is to download all ancillary files
    before going to an environment/system that does not have internet access.

    """
    if pooch_kwargs is None:
        pooch_kwargs = {}

    find_registerable_files()
    path = satpy.config.get('data_dir')
    pooch_obj = pooch.create(path, path, registry=_FILE_REGISTRY,
                             urls=_FILE_URLS)
    for fname in _FILE_REGISTRY:
        logger.info("Downloading extra data file '%s'...", fname)
        pooch_obj.fetch(fname, **pooch_kwargs)
    logger.info("Done downloading all extra files.")


def find_registerable_files():
    """Load all Satpy components so they can be downloaded."""
    _find_registerable_files_compositors()
    _find_registerable_files_readers()
    _find_registerable_files_writers()
    return sorted(_FILE_REGISTRY.keys())


def _find_registerable_files_compositors():
    """Load all compositor configs so that files are registered.

    Compositor objects should register files when they are initialized.

    """
    from satpy.composites.config_loader import CompositorLoader
    composite_loader = CompositorLoader()
    all_sensor_names = composite_loader.all_composite_sensors()
    composite_loader.load_compositors(all_sensor_names)


def _find_registerable_files_readers():
    """Load all readers so that files are registered."""
    import yaml
    from satpy.readers import configs_for_reader, load_reader
    for reader_configs in configs_for_reader():
        try:
            load_reader(reader_configs)
        except (ModuleNotFoundError, yaml.YAMLError):
            continue


def _find_registerable_files_writers():
    """Load all writers so that files are registered."""
    from satpy.writers import configs_for_writer, load_writer_configs
    for writer_configs in configs_for_writer():
        try:
            load_writer_configs(writer_configs)
        except ValueError:
            continue


class DataDownloadMixin:
    """Mixin class for Satpy components to download files.

    This class simplifies the logic needed to download and cache data files
    needed for operations in a Satpy component (readers, writers, etc). It
    does this in a two step process where files that might be downloaded are
    "registered" and then "retrieved" when they need to be used.

    To use this class include it as one of the subclasses of your Satpy
    component. Then in the ``__init__`` method, call the
    ``register_data_files`` function during initialization.

    .. note::

        This class is already included in the ``FileYAMLReader`` and
        ``Writer`` base classes. There is no need to define a custom
        class.

    The below code is shown as an example::

        from satpy.readers.yaml_reader import AbstractYAMLReader
        from satpy.data_download import DataDownloadMixin

        class MyReader(AbstractYAMLReader, DataDownloadMixin):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.register_data_files()

    This class expects data files to be configured in either a
    ``self.info['data_files']`` (standard for readers/writers) or
    ``self.config['data_files']`` list. The ``data_files`` item
    itself is a list of dictionaries. This information can also be
    passed directly to ``register_data_files`` for more complex cases.
    In YAML, for a reader, this might look like this::

        reader:
            name: abi_l1b
            short_name: ABI L1b
            long_name: GOES-R ABI Level 1b
            ... other metadata ...
            data_files:
              - url: "https://example.com/my_data_file.dat"
              - url: "https://raw.githubusercontent.com/pytroll/satpy/master/README.rst"
                known_hash: "sha256:5891286b63e7745de08c4b0ac204ad44cfdb9ab770309debaba90308305fa759"
              - url: "https://raw.githubusercontent.com/pytroll/satpy/master/RELEASING.md"
                filename: "satpy_releasing.md"
                known_hash: null

    In this example we register two files that might be downloaded.
    If ``known_hash`` is not provided or None (null in YAML) then the data
    file will not be checked for validity when downloaded. See
    :func:`~satpy.data_download.register_file` for more information. You can
    optionally specify ``filename`` to define the in-cache name when this file
    is downloaded. This can be useful in cases when the filename can not be
    easily determined from the URL.

    When it comes time to needing the file, you can retrieve the local path
    by calling ``~satpy.data_download.retrieve(cache_key)`` with the
    "cache key" generated during registration. These keys will be in the
    format: ``<component_type>/<filename>``. For a
    reader this would be ``readers/satpy_release.md``.

    This Mixin is not the only way to register and download files for a
    Satpy component, but is the most generic and flexible. Feel free to
    use the :func:`~satpy.data_download.register_file` and
    :func:`~satpy.data_download.retrieve` functions directly.
    However, :meth:`~satpy.data_download.find_registerable_files` must also
    be updated to support your component (if files are not register during
    initialization).

    """

    DATA_FILE_COMPONENTS = {
        'reader': 'readers',
        'writer': 'writers',
        'composit': 'composites',
    }

    @property
    def _data_file_component_type(self):
        cls_name = self.__class__.__name__.lower()
        for cls_name_sub, comp_type in self.DATA_FILE_COMPONENTS.items():
            if cls_name_sub in cls_name:
                return comp_type
        return 'other'

    def register_data_files(self, data_files=None):
        """Register a series of files that may be downloaded later.

        See :class:`~satpy.data_download.DataDownloadMixin` for more
        information on the assumptions and structure of the data file
        configuration dictionary.

        """
        comp_type = self._data_file_component_type
        if data_files is None:
            df_parent = getattr(self, 'info', self.config)
            data_files = df_parent.get('data_files', [])
        cache_keys = []
        for data_file_entry in data_files:
            cache_key = self._register_data_file(data_file_entry, comp_type)
            cache_keys.append(cache_key)
        return cache_keys

    def _register_data_file(self, data_file_entry, comp_type):
        url = data_file_entry['url']
        filename = data_file_entry.get('filename', os.path.basename(url))
        known_hash = data_file_entry.get('known_hash')
        return register_file(url, filename, component_type=comp_type,
                             known_hash=known_hash)
