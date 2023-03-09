# Vietnam results
There are substantive differences between the medium-resolution boundaries and the high-resolution boundaries; these areas are most prevalent in coastal islands and small, urban administrative units. 
## Interactive Map
<iframe src="_static/VNM_boundary_comparison.html" width=100% height=500px></iframe>

## Static examples
```{figure} images/VNM_Border_Comparison_HoChiMinh.png
:name: HoChiMinh

Border comparison in Ho Chi Minh, Vietnam
```
```{figure} images/VNM_Border_Comparison_NorthIslands.png
:name: TraBan

Border comparison in the Tra Ban Islands group, Vietnam
```

This leads to variation in cetrain zonal statistics in these areas. In this experiment we ran two zonal statistics:
1. [ESA Globcover](http://due.esrin.esa.int/page_globcover.php) - determine the majority landcover class in each district
2. [Nighttime Lights](https://registry.opendata.aws/wb-light-every-night/) - calculate sum of lights for most recent month (2023-02)

## ESA Globcover
This ~300m2 resolution landcover dataset classifies landcover into 23 categories.
```{figure} https://www.esa.int/var/esa/storage/images/esa_multimedia/images/2008/03/globcover_legend/9738784-3-eng-GB/GlobCover_legend_pillars.jpg
:name: Globcover_legend

Globcover legend
```
For each admin division we calculated the majority class and compared between the medium and high resolution datasets
```{figure} images/VNM_LC_Max.png
Major landcover class in medium-resolution boundaries. Red borders high-light admin divisions where the Landcover is different in the high resolution datasets.
```
Of the 681 admin 2 divisions in Vietnam, 12 have a different majority landcover class.

## Nighttime Lights
We calculated sum of lights for each dataset, and then compared them, as % change from medium-resolution boundary to high-resolution.
```{figure} images/VNM_NTL_SoL.png
Percent change in nighttime lights brightness from medium-resolution bounaries to high-resolution
```
| NTL change | Number of divisions |
| --- | :--- |
| Decreased by > 15% | 1 |
| Decreased by 5% to 15% | 13 |
| No change (-5% to 5%) | 635 |
| Increased by 5% to 15% | 19 |
| Increased by 15% to 50% | 6 |
| Increased by 50% to 100% | 4 |
| Increased by > 100% | 3 |

While most of the administrative divisions show little change (93%), many show substantive change, with 3 showing increase in brightness of > 100%


