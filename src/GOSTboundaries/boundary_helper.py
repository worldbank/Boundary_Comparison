import sys, os, importlib, json
import folium, shapely, rasterio

import contextily as ctx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
import geopandas as gpd

from rasterio.crs import CRS
from mpl_toolkits.axes_grid1 import make_axes_locatable
from h3 import h3
from shapely.geometry import Polygon, Point, mapping
from shapely.ops import unary_union
from urllib.request import urlopen
from tqdm import tqdm

import GOSTRocks.rasterMisc as rMisc
import GOSTRocks.ntlMisc as ntl
from GOSTRocks.misc import tPrint


class country_boundary():
    ''' Compare and attribute various country boundaries
    
        :param iso3: 3-character iso3 string for country (ie - KEN for Kenya)
        :type iso3: string
        :param official_wb_bounds: official bounds from the World Bank to be compared
        :type official_wb_bounds: class:`geopandas.GeoDataFrame`
        :param official_id_col: name of column in official_wb_bounds with unique id
        :type official_id_col: string
    '''
    def __init__(self, iso3, official_wb_bounds, official_id_col, out_folder = "/home/wb411133/projects/BOUNDARIES/{sel_iso3}", 
                    geoBounds='', geoBounds_id_col = 'shapeID', verbose=False):
        self.iso3 = iso3
        self.out_folder = out_folder.format(sel_iso3 = iso3)
        self.wb_id_col = official_id_col
        self.geoBounds_id_col = geoBounds_id_col
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
            
    def run_all(self, run_h3_summary=False, run_comparison=False, run_zonal=False, big_thresh=1000, h3_level=6,
                    esa_dataset = "/home/public/Data/GLOBAL/LANDCOVER/GLOBCOVER/2015/ESACCI-LC-L4-LCCS-Map-300m-P1Y-2015-v2.0.7.tif",
                    esa_legend = "/home/public/Data/GLOBAL/LANDCOVER/GLOBCOVER/2015/GLOBCOVER_LEGEND.csv"
            ):
        '''
        
            :param run_h3_summary: Evaluate h3 grid cells between boundary1 and boundary2, defaults is False
            :type run_h3_summary: boolean, optional
            :param h3_level: Level of h3 grid to create, default is 6
            :type h3_level: int, optional
            
            :param run_comparison: Run sliver comparison between boundary1 and boundary2, defaults is False
            :type run_comparison: boolean, optional
            :param big_thresh: Maximum size of sliver to be merged into neighbour boundary, default is 1000 m2
            :type big_thresh: int, optional
            
            :param run_zonal: Run zonal statistics on boundary1, boundary2, and h3_data (if it exists)
            :type run_zonal: boolean, optional
            :param esa_dataset: path to esa landcover dataset, default is JNB local
            :type esa_dataset: string, optional
            :param esa_legend: path to csv describing ESA landcover datasets, default is JNB local
            :type esa_legend: string, optional 
        
        '''
        if not "geo_match_id" in self.geoBounds.columns:
            # Attach medium resolution ID to high resolution dataset
            self.geoBounds = self.match_datasets(self.geoBounds, self.wb_bounds, self.geoBounds_id_col, self.wb_id_col, label="Matching bounds2 to bounds 1")

        # map difference between boundary 1 and boundary 2
        if run_comparison:
            xx = self.generate_boundary_difference(big_thresh=big_thresh)
        
        if run_h3_summary:
            try:
                h3_shape = self.h3_data.shape
            except:
                bounds1 = self.wb_bounds
                bounds2 = self.geoBounds
                
                # Generate h3 grid
                h3_data = self.generate_h3_grid(level=h3_level)
                # Attach medium resolution IDs to h3 grid
                h3_data = self.match_datasets(h3_data, bounds1, 'shape_id', self.wb_id_col, label="Matching h3 to bounds 1")
                h3_data.columns = ['geometry', 'shape_id', 'med_id', 'med_per'] 
                # Attach high resolution IDs to h3 grid
                h3_data = self.match_datasets(h3_data, bounds2, 'shape_id', "geo_match_id", label="Matching h3 to bounds 2")
                self.h3_data = h3_data
            
        if run_zonal:
            ntl_files = ntl.aws_search_ntl()
            inR = rasterio.open(esa_dataset)
            inL = pd.read_csv(esa_legend, quotechar='"')
            # Define the raster datasets to summarize within the admin boundaries
            file_defs = [
                [ntl_files[-1], 'NTL', 'N'],
                [inR, 'LC', 'C', inL['Value'].values],
            ]
            zonal_res = self.run_zonal(file_defs, z_geoB=True, z_wbB=True, z_corB=False)
            # Join the zonal res to the WB coarse boundaries
            wb_mapped = self.wb_bounds.copy()
            wb_mapped['NTL'] = zonal_res['NTL']['wbB']['NTL_SUM']

            wb_high = self.geoBounds.copy()
            wb_high['NTL_High'] = zonal_res['NTL']['geoB']['NTL_SUM'].values

            # Identify the major landcover class 
            wb_mapped['LC_MAX']    = zonal_res['LC']['wbB'].apply(lambda x: x.idxmax(), axis=1)
            wb_high['LC_MAX_High'] = zonal_res['LC']['geoB'].apply(lambda x: x.idxmax(), axis=1).values
            
            wb_mapped = wb_mapped.merge(wb_high.loc[:,['geo_match_id', 'NTL_High', 'LC_MAX_High']], left_on=self.wb_id_col, right_on='geo_match_id')
            # Determine % different in nighttime lights brightness
            wb_mapped['PER_NTL'] = wb_mapped.apply(lambda x: (x['NTL_High'] - x['NTL'])/x['NTL'], axis=1)
            # Determine the major Landcover class in the input dataset
            wb_mapped['LC_Match'] = wb_mapped.apply(lambda x: x['LC_MAX'] == x['LC_MAX_High'], axis=1)
            wb_mapped['LC_MAX'] = wb_mapped['LC_MAX'].astype(str)
            wb_mapped['LC_MAX_High'] = wb_mapped['LC_MAX'].astype(str)
            crs = wb_mapped.crs
            wb_mapped = wb_mapped.apply(pd.to_numeric, errors='ignore')
            
            self.wb_mapped = gpd.GeoDataFrame(wb_mapped, geometry='geometry', crs=crs)
    
    def ntl_summary(self, table_label = 'Number of districts with NTL change (medium to high)',
                          thresholds = [-1, -0.10, -0.02, 0.02, 0.10, 0.50, 1, 100], 
                          labels = ['< -10%',  '-10% to -2%', "No change", "2% to 10%", '10% to 50%', "50% to 100%", "> 100%"],
                          colors = ['#0571B0','#63A9CF',     '#F7F7F7',   "#F5A683",   "#D7604D"   , "#B3172B"    , "#67001F"],
                          legend_loc='upper right'):
        '''
        '''                
        ntl_change = self.wb_mapped.copy()        
        ntl_change[table_label] = pd.cut(ntl_change['PER_NTL'], thresholds, labels=labels)
        
        color_dict = dict(zip(labels, colors))            
        fig, ax = plt.subplots(figsize=(15,15))
        proj = CRS.from_epsg(3857)
        try:
            ntl_change = ntl_change.to_crs(proj)
        except:
            ntl_change.crs = 4326
            ntl_change = ntl_change.to_crs(proj)            
        #divider = make_axes_locatable(ax)
        #cax = divider.append_axes("right", size="5%", pad=0.1)
        all_labels = []
        for ctype, data in ntl_change.groupby(table_label)    :
            color = color_dict[ctype]
            if data.shape[0] > 0:
                data.plot(color=color, ax=ax, label=ctype, linewidth=0.2)
                cur_patch = mpatches.Patch(color=color, label=f'{ctype} [{data.shape[0]}]')
                all_labels.append(cur_patch)

        ctx.add_basemap(ax, source=ctx.providers.Stamen.TonerBackground, crs=proj) #zorder=-10, 'EPSG:4326'
        ax.legend(handles=all_labels, loc=legend_loc)
        ax = ax.set_axis_off()
                
        return([ax, ntl_change.groupby([table_label])['OBJECTID'].count()])
    
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
        
    def generate_h3_grid(self, level=6):
        ''' Create the h3 hexabin grid for the selected admin datasets; join the admin datasets 
        '''
        try:
            del final_hexs
        except:
            pass

        for cPoly in (self.wb_bounds.unary_union):
            all_hexs = list(h3.polyfill(cPoly.__geo_interface__, level, geo_json_conformant=True))
            try:        
                final_hexs = final_hexs + all_hexs
            except:
                final_hexs = all_hexs
                
            final_hexs = list(set(final_hexs))
            
        hex_poly = lambda hex_id: Polygon(h3.h3_to_geo_boundary(hex_id, geo_json=True))
        all_polys = gpd.GeoSeries(list(map(hex_poly, final_hexs)), index=final_hexs, crs="EPSG:4326")
        all_polys = gpd.GeoDataFrame(all_polys, crs=4326, columns=['geometry'])
        all_polys['shape_id'] = list(all_polys.index)
        
        self.h3_grid = all_polys
        
        return(all_polys)

        
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
        
    def map_boundary_comparison(self, start_location, zoom_level, buffer_dist=0.1):
        ''' generate folium map comparing boundaries
        '''
        bounds1 = self.wb_bounds.loc[self.wb_bounds.intersects(start_location.buffer(buffer_dist))]        
        bounds2 = self.geoBounds.loc[self.geoBounds.intersects(start_location.buffer(buffer_dist))]
        
        m = folium.Map(location=[start_location.y,start_location.x], zoom_start=zoom_level, tiles="stamentoner", control_scale=True)
        # add the bounds1 lines as red lines
        for idx, row in bounds1.iterrows():
            wb_shp = folium.GeoJson(mapping(row['geometry']), name='Medium', style_function=lambda feature: {
                'fillColor':'#FF000000',
                'color':'#FF2D00',
                'opacity':0.7,
                'weight':3
            }) 
            wb_shp.add_to(m)

            
        # add the bounds2 lines as blue lines
        for idx, row in bounds2.iterrows():
            wb_shp = folium.GeoJson(mapping(row['geometry']), name='High', style_function=lambda feature: {
                'fillColor':'#FF000000',
                'color':'#000AFF',
                'opacity':0.5,
                'weight':3
            }) 
            wb_shp.add_to(m)

        # folium.LayerControl(collapsed=True).add_to(m)
        return(m)

    def static_map_lc(self, sub='', map_epsg=3857, legend_loc='upper right',
                        esa_legend = "/home/public/Data/GLOBAL/LANDCOVER/GLOBCOVER/2015/GLOBCOVER_LEGEND.csv"):
        ''' generate a static map of the Landcover zonal results        
        '''
        if sub == '':
            try:
                sub = self.wb_mapped.copy()
            except:
                raise(ValueError("Need to run_zonal or proivde a DF for mapping"))
        try:
            sub = sub.to_crs(map_epsg)
        except:
            sub.crs = 4326
            sub = sub.to_crs(map_epsg)
        # Create dictionary of mapping values
        esa_legend = "/home/public/Data/GLOBAL/LANDCOVER/GLOBCOVER/2015/GLOBCOVER_LEGEND.csv"
        esa_data = pd.read_csv(esa_legend)
        esa_data['Value'] = esa_data['Value'].apply(lambda x: f'LC_{x}')
        esa_dict   = dict(zip(esa_data['Value'], esa_data['Hex']))
        esa_labels = dict(zip(esa_data['Value'], esa_data['Shortname']))

        fig, ax = plt.subplots(figsize=(15,15))
        proj = CRS.from_epsg(map_epsg)
        #divider = make_axes_locatable(ax)
        #cax = divider.append_axes("right", size="5%", pad=0.1)
        sel_mixed = sub.loc[sub['LC_Match'] == False].copy()
        mismatch_color = 'pink'
        mismatch_edge = 'darkred'
        cur_patch = mpatches.Patch(facecolor=mismatch_color, edgecolor=mismatch_edge, hatch="///", label=f"Mismatch [{sel_mixed.shape[0]}]")
        all_labels = [cur_patch]
        for ctype, data in sub.groupby("LC_MAX")    :
            color = esa_dict[ctype]
            data.plot(color=color, ax=ax, label=ctype, linewidth=0.2)
            cur_patch = mpatches.Patch(color=color, label=f'{esa_labels[ctype]} [{data.shape[0]}]')
            all_labels.append(cur_patch)
        # Add outline of features with mismatch
        sel_mixed.plot(color=mismatch_color, edgecolor=mismatch_edge, hatch="//////", ax=ax, label=False, linewidth=4)
        
        ctx.add_basemap(ax, source=ctx.providers.Stamen.TonerBackground, crs=proj) #zorder=-10, 'EPSG:4326'
        ax.legend(handles=all_labels, loc=legend_loc)
        ax = ax.set_axis_off()
        return(ax)
        
    def static_map_h3(self, sub='', map_epsg=3857, legend_loc='upper right'):
        ''' generate a static map of the Landcover zonal results        
        '''
        if sub == '':
            try:
                sub = self.h3_data.copy()
            except:
                raise(ValueError("Need to run_zonal or proivde a DF for mapping"))
        sub = sub.to_crs(map_epsg)
        # Create dictionary of mapping values
        sub['h3_match'] = sub.apply(lambda x: str(x['med_id'] == x['geo_match_id']), axis=1)
        
        h3_dict   = {'False': '#B3172B', 'True':'#FFFFFF'}       
        edge_dict = {'False': '#B3172B', 'True':'#808080'}       
        fig, ax = plt.subplots(figsize=(15,15))
        proj = CRS.from_epsg(map_epsg)
        #divider = make_axes_locatable(ax)
        #cax = divider.append_axes("right", size="5%", pad=0.1)
        all_labels = []
        for ctype, data in sub.groupby("h3_match")    :
            color = h3_dict[ctype]
            data.plot(color=color, ax=ax, label=ctype, linewidth=0.2, edgecolor=edge_dict[ctype])
            cur_patch = mpatches.Patch(facecolor=color, label=f'{ctype} [{data.shape[0]}]', edgecolor=edge_dict[ctype])
            all_labels.append(cur_patch)

        ctx.add_basemap(ax, source=ctx.providers.Stamen.TonerBackground, crs=proj) #zorder=-10, 'EPSG:4326'
        ax.legend(handles=all_labels, loc=legend_loc)
        ax = ax.set_axis_off()
        return(ax)

    def match_datasets(self, inD1, inD2, inD1_col, inD2_col, label='Matching Datasets'):
        ''' Attach unique IDs between two admin datasets. For each dataset, identify primary match in dataset 2, and some information describing the intersection
        
            :param inD1: administrative dataset
            :type inD1: class geoPandas.GeoDataframe
        '''
        inD1['geo_match_id'] = ''
        inD1['geo_match_per'] = 0.0
        for idx, row in tqdm(inD1.iterrows(), total=inD1.shape[0], desc=label):
            selD2 = inD2.loc[inD2.intersects(row['geometry'])].copy()
            selD2['iArea'] = 0.0
            for idx2, row2 in selD2.iterrows():
                per_overlap = (row['geometry'].intersection(row2['geometry']).area)/(row['geometry'].area)
                selD2.loc[idx2, 'iArea'] = per_overlap
            selD2 = selD2.sort_values('iArea', ascending=False)
            inD1.loc[idx,'geo_match_id']  = selD2[inD2_col].iloc[0]
            inD1.loc[idx,'geo_match_per'] = selD2['iArea'].iloc[0]
        crs = inD1.crs        
        inD1 = inD1.apply(pd.to_numeric, errors='ignore')        
        inD1 = gpd.GeoDataFrame(inD1, geometry='geometry', crs=crs)
        return(inD1)
    
    def run_zonal(self, file_defs, z_geoB=True, z_wbB=True, z_corB=False, z_h3=False):
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
        if z_h3:
            try:
                h3_grid = self.h3_grid
            except:
                h3_grid = self.generate_h3_grid()
            
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
                    geo_res = rMisc.zonalStats(geoB, curR, rastType=file_def[2], reProj=True)
                    geo_res = gpd.GeoDataFrame(geo_res, columns = [f'{name}_{x}' for x in ['SUM', 'MIN', 'MAX', 'MEAN']])
                if z_wbB:
                    geo_res_wb = rMisc.zonalStats(wbB, curR, rastType=file_def[2], reProj=True)
                    geo_res_wb = gpd.GeoDataFrame(geo_res_wb, columns = [f'{name}_{x}' for x in ['SUM', 'MIN', 'MAX', 'MEAN']])
                if z_corB:
                    geo_res_cor = rMisc.zonalStats(corB, curR, rastType=file_def[2], reProj=True)
                    geo_res_cor = gpd.GeoDataFrame(geo_res_cor, columns = [f'{name}_{x}' for x in ['SUM', 'MIN', 'MAX', 'MEAN']])
                if z_h3:
                    geo_res_h3 = rMisc.zonalStats(h3_grid, curR, rastType=file_def[2], reProj=True)
                    geo_res_h3 = gpd.GeoDataFrame(geo_res_h3, columns = [f'{name}_{x}' for x in ['SUM', 'MIN', 'MAX', 'MEAN']])
            else:
                if z_geoB:
                    geo_res = rMisc.zonalStats(geoB, curR, rastType=file_def[2], unqVals=file_def[3], reProj=True)
                    geo_res = gpd.GeoDataFrame(geo_res, columns = [f'{name}_{x}' for x in file_def[3]])
                if z_wbB:
                    geo_res_wb = rMisc.zonalStats(wbB, curR, rastType=file_def[2], unqVals=file_def[3], reProj=True)
                    geo_res_wb = gpd.GeoDataFrame(geo_res_wb, columns = [f'{name}_{x}' for x in file_def[3]])                    
                if z_corB:
                    geo_res_cor = rMisc.zonalStats(corB, curR, rastType=file_def[2], unqVals=file_def[3], reProj=True)
                    geo_res_cor = gpd.GeoDataFrame(geo_res_cor, columns = [f'{name}_{x}' for x in file_def[3]])
                if z_corB:
                    geo_res_h3 = rMisc.zonalStats(h3_grid, curR, rastType=file_def[2], unqVals=file_def[3], reProj=True)
                    geo_res_h3 = gpd.GeoDataFrame(geo_res_h3, columns = [f'{name}_{x}' for x in file_def[3]])
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
            try:
                final[name]['h3'] = geo_res_h3
            except:
                pass
        return(final)
                            
    def write_output(self, output_folder, write_slivers=True, write_base=True):
        ''' write output data to a single folder
        '''
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        try:
            self.h3_data.to_file(os.path.join(output_folder, 'h3_grid.geojson'), driver="GeoJSON")
        except:
            pass
        
        if write_base:
            self.wb_bounds.to_file(os.path.join(output_folder, 'WB_bounds.geojson'), driver="GeoJSON")
            self.geoBounds.to_file(os.path.join(output_folder, 'GEO_bounds.geojson'), driver="GeoJSON")
        try:
            self.corrected_geo.to_file(os.path.join(output_folder, 'GEO_CORRECTED_bounds.geojson'), driver="GeoJSON")
        except:
            pass
            
        try:
            self.wb_mapped.to_file(os.path.join(output_folder, 'WB_bounds_zonal.geojson'), driver="GeoJSON")
        except:
            pass
        if write_slivers:
            self.wb_sliver_df.to_file(os.path.join(output_folder, 'WB_slivers.geojson'), driver="GeoJSON")
            try:
                self.big_slivers.to_file(os.path.join(output_folder, 'BIG_slivers.geojson'), driver="GeoJSON")
            except:
                pass    
            
        