from osgeo import gdal
from pyproj import Proj
import numpy as np

import os
import re


class LandsatReader(object):
    def __init__(self,
                 landsat_root,
                 line_sample_roi=None):
        self.root = landsat_root
        self.lsr = line_sample_roi
        self.dn_data_container = dict()

    def _get_file_list(self, data_file):
        files = os.listdir(os.path.join(self.root, data_file))
        self.file_list = [os.path.join(self.root, data_file, f)
                          for f in files if "TIF" in f if "BQA" not in f if "B8" not in f]

    def _read_arrays(self):
        for f in self.file_list:
            if "B" in f[-6:]:
                data_key = self._get_container_key_a(f)
            else:
                data_key = self._get_container_key_b(f)
            gdal.UseExceptions()
            ds = gdal.Open(f)
            self.dn_data_container[data_key] = self._extract_roi(ds)

    def _get_container_key_a(self, f):
        return re.search('B([0-9])', f).group()

    # fix this later
    def _get_container_key_b(self, f):
        return re.search('B([1][0-1])', f).group()

    def _extract_roi(self, ds):
        return ds.GetRasterBand(1).ReadAsArray(self.lsr['x1'],
                                               self.lsr['y1'],
                                               self.lsr['x2'] - self.lsr['x1'],
                                               self.lsr['y2'] - self.lsr['y1'])

    def read(self, data_file):
        self._get_file_list(data_file)
        self._read_arrays()


class LandsatGeoReader(object):
    def __init__(self,
                 landsat_root,
                 proj_param,
                 line_sample_roi=None):
        self.root = landsat_root
        self.proj_param = proj_param
        self.lsr = line_sample_roi
        self.geo_data_container = dict()

    def _get_file(self, data_file):
        files = os.listdir(os.path.join(self.root, data_file))
        self.f = [os.path.join(self.root, data_file, f) for f in files if "B2" in f][0]

    def _read_geo(self):
        gdal.UseExceptions()
        ds = gdal.Open(self.f)
        gt = self._get_transform(ds)
        print self.f, gt
        grids = self._construct_grids()
        self.compute_geo(gt, grids)

    def _get_transform(self, ds):
        return ds.GetGeoTransform()

    def _construct_grids(self):
        # create grid the size of the image
        x = np.arange(self.lsr['x1'], self.lsr['x2'], 1)
        y = np.arange(self.lsr['y1'], self.lsr['y2'], 1)
        return np.meshgrid(x, y)

    def compute_geo(self, gt, grids):
        # compute eastings and northings
        x = gt[0] + grids[0] * gt[1] + grids[1] * gt[2]
        y = gt[3] + grids[0] * gt[4] + grids[1] * gt[5]

        # convert to wgs84
        landsat_proj = Proj(self.proj_param)
        lon, lat = landsat_proj(x, y, inverse=True)
        self.geo_data_container['lon'] = lon
        self.geo_data_container['lat'] = lat
        print np.min(x), np.min(lon), np.max(x), np.max(lon)
        print np.min(y), np.min(lat), np.max(y), np.max(lat)

    def _extract_roi(self, ds):
        return ds.GetRasterBand(1).ReadAsArray(self.lsr['x1'],
                                               self.lsr['y1'],
                                               self.lsr['x2'] - self.lsr['x1'],
                                               self.lsr['y2'] - self.lsr['y1'])

    def read(self, data_file):
        self._get_file(data_file)
        self._read_geo()


class LandsatMetaReader(object):
    def __init__(self,
                 landsat_root,
                 srf_path=''):
        self.root = landsat_root
        self.meta_data_container = dict()
        self._centre_wavelengths()

        if srf_path:
            self.srf_path = srf_path
            self._spectral_response_functions()

    def _centre_wavelengths(self):
        d = dict()
        keys = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B9"]
        values = [0.443, 0.482, 0.561, 0.655, 0.865, 1.609, 2.201, 1.373]  # microns
        for k, v in zip(keys, values):
            d[k] = v
        self.meta_data_container["centre_wavelengths"] = d

    def _spectral_response_functions(self):
        srf_dict = dict()
        for f in os.listdir(self.srf_path):
            if "_" in f:
                continue
            srf = self._read_srf(self.srf_path + f)
            f = f.split(".")
            srf_dict[f[0]] = srf
        self.meta_data_container['srf'] = srf_dict

    def _read_srf(self, srf_path):
        wvls = np.genfromtxt(srf_path, usecols=(0), delimiter='', dtype=float) / 1000  # convert to microns
        rsps = np.genfromtxt(srf_path, usecols=(1), delimiter='', dtype=float)
        srf = {}
        srf["wavelengths"] = wvls
        srf["responses"] = rsps
        return srf

    def _get_file(self, data_file):
        files = os.listdir(os.path.join(self.root, data_file))
        self.f = [os.path.join(self.root, data_file, f) for f in files if "MTL.txt" in f][0]

    def _read_meta(self):
        with open(self.f) as f:
            for line in f:
                listedline = line.strip().split(' = ')  # split around the = sign
                if len(listedline) > 1:  # we have the = sign in there
                    self.meta_data_container[listedline[0]] = listedline[1]

    def read(self, data_file):
        self._get_file(data_file)
        self._read_meta()


def main():
    landsat_path = "/Users/danielfisher/Projects/nrgi-mining-concessions/data/raw/Landsat/"
    landsat_proj_param = "+init=EPSG:32617"  # http://spatialreference.org/ref/epsg/32618/
    landsat_pixel_roi = {"x1": 3300,
                         "x2": 3900,
                         "y1": 2700,
                         "y2": 3200}

    image_data_reader = LandsatReader(landsat_path, landsat_pixel_roi)
    geo_data_reader = LandsatGeoReader(landsat_path, landsat_proj_param, landsat_pixel_roi)
    meta_data_reader = LandsatMetaReader(landsat_path)

    ls_filenames = os.listdir(landsat_path)
    for ls_filename in ls_filenames:

        try:
            image_data_reader.read(ls_filename)
            geo_data_reader.read(ls_filename)
            meta_data_reader.read(ls_filename)
        except Exception, e:
            print "Could not open ", ls_filename, "with error", e

        image_data = image_data_reader.dn_data_container
        geo_data = geo_data_reader.geo_data_container
        meta_data = meta_data_reader.meta_data_container



if __name__ == "__main__":
    main()