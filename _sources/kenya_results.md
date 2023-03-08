# Kenya results
There are substantive differences between the medium-resolution boundaries and the high-resolution boundaries; these areas are most prevalent in coastal islands and small, urban administrative units. 
## Interactive Map
<iframe src="_static/KEN_boundary_comparison.html" width=100% height=500px></iframe>

## Static examples
```{figure} images/KEN_Border_Comparison_Nairboi.png
:name: Nairobi

Border comparison in Nairobi, Vietnam
```
```{figure} images/KEN_Border_Comparison_SouthCoast.png
:name: SouthCoast

Border comparison in the Southern coast of Kenya, near Tanzania
```

This leads to variation in cetrain zonal statistics in these areas. In this experiment we ran two zonal statistics:
1. [ESA Globcover](http://due.esrin.esa.int/page_globcover.php) - determine the majority landcover class in each district
2. [Nighttime Lights](https://registry.opendata.aws/wb-light-every-night/) - calculate sum of lights for most recent month (2023-02)

## ESA Globcover
For each admin division we calculated the majority class and compared between the medium and high resolution datasets
```{figure} images/KEN_LC_Max.png
Major landcover class in medium-resolution boundaries. Red borders high-light admin divisions where the Landcover is different in the high resolution datasets.
```
Of the 290 admin 2 divisions in Vietnam, only 1 has a different majority landcover class.

## Nighttime Lights
We calculated sum of lights for each dataset, and then compared them, as % change from medium-resolution boundary to high-resolution.
```{figure} images/KEN_NTL_SoL.png
Percent change in nighttime lights brightness from medium-resolution bounaries to high-resolution
```
| NTL change | Number of divisions |
| --- | :--- |
| Decreased by > 15% | 1 |
| Decreased by 5% to 15% | 7 |
| No change (-5% to 5%) | 272 |
| Increased by 5% to 15% | 6 |
| Increased by 15% to 50% | 4 |

While most of the administrative divisions show little change (94%), many show substantive change, with 4 showing an increase in brightness of almost 50%
