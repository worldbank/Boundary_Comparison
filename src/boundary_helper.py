import sys, os, importlib, json
import folium, shapely, rasterio

import pandas as pd
import geopandas as gpd

from shapely.geometry import Polygon, Point, mapping
from shapely.ops import unary_union
from urllib.request import urlopen

import GOSTRocks.rasterMisc as rMisc
from GOSTRocks.misc import tPrint


class country_boundary():
    ''' Compare and attribute various country boundaries
    
        :param iso3: 3-character iso3 string for country (ie - KEN for Kenya)
        :type iso3: string
        :param official_wb_bounds: official bounds from the World Bank to be compared
        :type official_wb_bounds: class:`geopandas.GeoDataFrame`
    '''
    def __init__(self, iso3, official_wb_bounds, out_folder = "/home/wb411133/projects/BOUNDARIES/{sel_iso3}", geoBounds='', verbose=False):
        self.iso3 = iso3
        self.out_folder = out_folder.format(sel_iso3 = iso3)
        if not os.path.exists(self.out_folder):
            os.makedirs(self.out_folder)
            
        if geoBounds.__class__ == gpd.GeoDataFrame:
            self.geoBounds = geoBounds        
        else:
            self.geoBounds = self.get_geobounds()
        
        self.wb_bounds = official_wb_bounds
        if self.wb_bounds.crs != self.geoBounds.crs:
            raise(ValueError("CRS do not match between Geoboundaris and official boundaries"))
        self.verbose=verbose
            
    def get_geobounds(self, geobounds_url = 'https://www.geoboundaries.org/api/current/gbOpen/{iso3}/ADM{lvl}/', lvl=2):
        ''' access the geoboundaries al the defined level
        
            :param geobounds_url: url path to download geobounds from github, defaults to 'https://www.geoboundaries.org/api/current/gbOpen/{iso3}/ADM{lvl}/'
            :type geobounds_url: string, optional
            :param lvl: admin boundary to download, defaults to 2
            :type lvl: int, optional
        '''
        # Download adm2 from geoboundaries
        response = urlopen(geobounds_url.format(iso3=self.iso3,lvl=lvl))
        data_json = json.loads(response.read())
        adm2_url = data_json['gjDownloadURL']

        geoBounds = gpd.read_file(adm2_url)
        geoBounds.to_crs(4326)
        return(geoBounds)
        
    def generate_boundary_difference(self, area_crs=3857, inGeo_id='shapeID', big_thresh=100, verbose=False):
        ''' Generate difference objects between wb_bounds and geo_bounds
        
            :param area_crs: epsg code for crs for measuring area of slivers, default is 3857 (web-mercator)
            :type area_crs: int, optional
            :param inGeo_id: column in geoboundaries with unique ID, default is 'shapeISO'
            :type inGeo_id: string, optional
            :param big_thresh: area threshold for calculating big differences between the datasets.
                small differences are merged automatically; big differences are returned to deal with manually, 
                default is big_thresh
            :type big_thresh: int, optional
        '''
        # Generate slivers, or holes in the geobounds that are in the WB bounds
        inGeo = self.geoBounds
        wb_slivers = self.wb_bounds.unary_union.difference(inGeo.unary_union)
        cnt = 0
        all_res = []
        for sliver in list(wb_slivers):
            all_res.append([cnt, sliver, sliver.area])
            
        wb_sliver_df = gpd.GeoDataFrame(pd.DataFrame(all_res, columns=['ID','geometry','area']), geometry='geometry', crs=4326)
        wb_sliver_df = wb_sliver_df.to_crs(area_crs)
        wb_sliver_df['area'] = wb_sliver_df['geometry'].apply(lambda x: x.area/1000000)
        wb_sliver_df = wb_sliver_df.to_crs(4326)
        self.big_slivers = wb_sliver_df.loc[wb_sliver_df['area'] > big_thresh]
        wb_sliver_df = wb_sliver_df.loc[wb_sliver_df['area'] < big_thresh ]
        self.wb_sliver_df = wb_sliver_df
        
        # For each sliver, determine the admin section in in_geo to merge it into        
        wb_sliver_df['geoID'] = ''
        for idx, row in wb_sliver_df.iterrows():
            sel_geo = inGeo.loc[inGeo.intersects(row['geometry'].buffer(0.01))].copy()
            if sel_geo.shape[0] == 1: 
                wb_sliver_df.loc[idx, 'geoID'] = sel_geo[inGeo_id].values[0]
            elif sel_geo.shape[0] > 1:
                # If it intersects two admins, figure out which one if intersects more
                sel_geo['area'] = sel_geo['geometry'].apply(lambda x: x.intersection(row['geometry'].buffer(0.01)).area)
                wb_sliver_df.loc[idx, 'geoID'] = sel_geo.sort_values('area', ascending=False).iloc[0][inGeo_id]
            else:
                if verbose:
                    print(f"{idx} in slivers does not intersect geo_bounds")
                else:
                    pass
                
        # Loop through the geo_bounds
        edit_geo = inGeo.copy()
        for idx, row in edit_geo.iterrows():
            # Clip shape to national boundary
            new_shape = row['geometry'].intersection(self.wb_bounds.unary_union)                
            # Select all the slivers to merge into the current admin area
            sel_slivers = wb_sliver_df.loc[wb_sliver_df['geoID'] == row[inGeo_id]]
            if sel_slivers.shape[0] > 0:
                new_shape = new_shape.union(unary_union(sel_slivers['geometry']).buffer(0.0001))
            row['geometry'] = new_shape
            edit_geo.loc[idx] = row
                
        self.corrected_geo = edit_geo
        return(edit_geo)
        
    def generate_summary_difference(self, area_crs=3857, verbose=True):
        ''' summarize the differences between the WB bounds and the GeoBounds:
            1. numbers of features
            2. total area
            3. Area in WB bounds missing in GeoBounds (wb_slivers)
            4. Area in geobounds missing in WB bounds 
        '''
        wb_features = self.wb_bounds.shape[0]
        wb_area = self.wb_bounds.unary_union.area
        
        geo_features = self.geoBounds.shape[0]
        geo_area = self.geoBounds.unary_union.area
        
        wb_per = wb_area/geo_area * 100
        
        wb_sliver_area = self.wb_sliver_df.to_crs(area_crs).unary_union.area
        if self.big_slivers.shape[0] > 0:
            wb_sliver_area = wb_sliver_area + self.big_slivers.to_crs(area_crs).unary_union.area
        
        wb_holes = self.geoBounds.unary_union.difference(self.wb_bounds.unary_union)
        wb_holes_area = wb_holes.area
        
        self.comp_summary = [wb_area, geo_area, wb_features, geo_features, wb_sliver_area, wb_holes_area, self]
        
        if verbose:
            print(f"{self.iso3}: Total area of WB bounds is {round(wb_per, 2)}% of geobounds")
        
        return(self.comp_summary)       
    
    def map_corrected_bounds(self, geobounds_label='GeoBounds'):
        ''' generate folium map comparing boundaries
        '''
        selWB = self.wb_bounds
        edit_geo = self.corrected_geo
        
        m = folium.Map(location=[selWB.centroid.y.values[0], selWB.centroid.x.values[0]], zoom_start=7, tiles="stamentoner", control_scale=True)
        # add the official World Bank boundaries to the map as a single, yellow polygon
        wb_shp = folium.GeoJson(mapping(selWB.unary_union), name='WB', style_function=lambda feature: {
            'color':'yellow',
            'weight':4
        }) 
        wb_shp.add_to(m)

        # add the original geobounds to the map as a blue polygon
        in_geo_shp = folium.GeoJson(mapping(self.geoBounds.unary_union), name=geobounds_label, style_function=lambda feature: {
            'color':'blue',
            'weight':0.5
        }) 
        in_geo_shp.add_to(m)

        '''
        # add the slivers to the map                
        in_geo_shp = folium.GeoJson(mapping(self.wb_sliver_df.unary_union), name='Slivers', style_function=lambda feature: {
            'color':'green',
            'weight':5
        }) 
        in_geo_shp.add_to(m)
        
        # add the big slivers to the map                
        in_geo_shp = folium.GeoJson(mapping(self.big_slivers.unary_union), name='Big Slivers', style_function=lambda feature: {
            'color':'orange',
            'weight':5
        }) 
        in_geo_shp.add_to(m)
        # add the correct geo_bounds one by one as red
        geo_bounds = folium.GeoJson(mapping(edit_geo.unary_union), name=f'{geobounds_label} corrected', style_function=lambda feature: {
            'color':'red',
            'weight':1
        })
        geo_bounds.add_to(m)
        '''
        folium.LayerControl(collapsed=True).add_to(m)
        return(m)
        
    def match_datasets(self, inD1, inD2, inD1_col, inD2_col):
        ''' Attach unique IDs between two admin datasets. For each dataset, identify primary match in dataset 2, and some information describing the intersection
        
            :param inD1: administrative dataset
            :type inD1: class geoPandas.GeoDataframe
        '''
        inD1['geo_match_id'] = ''
        inD1['geo_match_per'] = 0.0
        for idx, row in inD1.iterrows():
            selD2 = inD2.loc[inD2.intersects(row['geometry'])].copy()
            selD2['iArea'] = 0.0
            for idx2, row2 in selD2.iterrows():
                per_overlap = (row['geometry'].intersection(row2['geometry']).area)/(row['geometry'].area)
                selD2.loc[idx2, 'iArea'] = per_overlap
            selD2 = selD2.sort_values('iArea', ascending=False)
            inD1.loc[idx,'geo_match_id']  = selD2[inD2_col].iloc[0]
            inD1.loc[idx,'geo_match_per'] = selD2['iArea'].iloc[0]
    
        return(inD1)
    
    def run_zonal(self, file_defs, z_geoB=True, z_wbB=True, z_corB=False):
        ''' run zonal stats using the official WB boundaries, the original geobounds, and the corrected geobounds
        
        :param file_defs: list of raster files to process; each list item is [file_def, name, type, (optional) expected vals]
        :type file_defs: [class rasterio.io.DatasetReader, str, str, list of ints]
        :param z_geoB, z_wbB, z_corB: boolean flags to run zonal stats on the input datasets
        '''
        geoB = self.geoBounds
        try:
            corB = self.corrected_geo
        except:
            pass
        wbB = self.wb_bounds
        final = {}
        for file_def in file_defs:
            if self.verbose:
                tPrint(f"Runnning zonal on {file_def[1]}")
            curR = file_def[0]
            if type(curR) == str:
                curR = rasterio.open(curR)
            name = file_def[1]
            if file_def[2] == 'N':
                if z_geoB:
                    geo_res = rMisc.zonalStats(geoB, curR, rastType=file_def[2])
                    geo_res = gpd.GeoDataFrame(geo_res, columns = [f'{name}_{x}' for x in ['SUM', 'MIN', 'MAX', 'MEAN']])
                if z_wbB:
                    geo_res_wb = rMisc.zonalStats(wbB, curR, rastType=file_def[2])
                    geo_res_wb = gpd.GeoDataFrame(geo_res_wb, columns = [f'{name}_{x}' for x in ['SUM', 'MIN', 'MAX', 'MEAN']])
                if z_corB:
                    geo_res_cor = rMisc.zonalStats(corB, curR, rastType=file_def[2])
                    geo_res_cor = gpd.GeoDataFrame(geo_res_cor, columns = [f'{name}_{x}' for x in ['SUM', 'MIN', 'MAX', 'MEAN']])
            else:
                if z_geoB:
                    geo_res = rMisc.zonalStats(geoB, curR, rastType=file_def[2], unqVals=file_def[3])
                    geo_res = gpd.GeoDataFrame(geo_res, columns = [f'{name}_{x}' for x in file_def[3]])
                if z_wbB:
                    geo_res_wb = rMisc.zonalStats(wbB, curR, rastType=file_def[2], unqVals=file_def[3])
                    geo_res_wb = gpd.GeoDataFrame(geo_res_wb, columns = [f'{name}_{x}' for x in file_def[3]])                    
                if z_corB:
                    geo_res_cor = rMisc.zonalStats(corB, curR, rastType=file_def[2], unqVals=file_def[3])
                    geo_res_cor = gpd.GeoDataFrame(geo_res_cor, columns = [f'{name}_{x}' for x in file_def[3]])
            final[name] = {}
            try:
                final[name]['geoB'] = geo_res
            except:
                pass
            try:
                final[name]['wbB'] = geo_res_wb
            except:
                pass
            try:
                final[name]['corB'] = geo_res_cor
            except:
                pass
        return(final)
                
            

    def write_output(self, output_folder, write_slivers=True, write_base=True):
        ''' write output data to a single folder
        '''
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            
        if write_base:
            self.wb_bounds.to_file(os.path.join(output_folder, 'WB_bounds.geojson'), driver="GeoJSON")
            self.geoBounds.to_file(os.path.join(output_folder, 'GEO_bounds.geojson'), driver="GeoJSON")
        self.corrected_geo.to_file(os.path.join(output_folder, 'GEO_CORRECTED_bounds.geojson'), driver="GeoJSON")
        if write_slivers:
            self.wb_sliver_df.to_file(os.path.join(output_folder, 'WB_slivers.geojson'), driver="GeoJSON")
            try:
                self.big_slivers.to_file(os.path.join(output_folder, 'BIG_slivers.geojson'), driver="GeoJSON")
            except:
                pass    
            
        