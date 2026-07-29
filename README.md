# Flood Risk Exposure Mapping for Energy Resources

> Combining flood, terrain and energy-asset data to map the exposure of substations and distributed energy resources in the Durham area, supported by a reproducible data and visualisation workflow.

| EPSRC-funded [Vacation Internship](https://www.ukri.org/what-we-do/developing-people-and-skills/research-skills-initiatives/apprenticeships-internships-and-placements/internships-and-placements/) Project |
| :--- |
| Associated with the UKRI grant: "Satellite-Aided Technologies for advancing resilience - Guarding energy services under climate hazards, risks, and disasters (SAT-Guard)" [UKRI Gateway](https://gtr.ukri.org/projects?ref=MR%2FZ50578X%2F1) |
| Student Research Associates: [Isabelle Servonat][servonat], [Oscar Ryley][ryley] |
| Supervisors: [Prof. Hongjian Sun][sun], [Dr Wenzhu Li][li], and [Dr Misael Alpizar Santana][santana] |

[servonat]: https://www.linkedin.com/in/isabelleservonat/
[ryley]: https://oryley.com/
[sun]: https://www.durham.ac.uk/staff/hongjian-sun/
[li]: https://www.durham.ac.uk/staff/wenzhu-li/
[santana]: https://www.durham.ac.uk/staff/misael-alpizar-santana/


## Live Site - [powergrid.oryley.com](https://powergrid.oryley.com)

[![alt text](public/data/images/screenshot.png)](https://powergrid.oryley.com)


## Data

> ### Initial Sources
> - Renewable: [Renewables.ninja](https://www.renewables.ninja/)
> - Hazard-Energy: [Hazard-Energy Interrelationship Matrix](https://tageleaschale.shinyapps.io/deploy-app-3/)
> - Past Weather Events: [Met Office, Past Weather Events](https://weather.metoffice.gov.uk/learn-about/past-uk-weather-events)
> - NASA Earth Data: [earthdata.nasa.gov](https://www.earthdata.nasa.gov/)


### 📁 Directory Structure

```text
data/
├── images/
├── substation_sites_list.geojson
└── county_durham.geojson
```

- `substation_sites_list.geojson`: [Northern Power Grid Open Data](https://northernpowergrid.opendatasoft.com/explore/dataset/substation_sites_list/export/?disjunctive.dno_area)
- `county_durham.geojson`: [MapIt Durham County Council Area - ID 2223](https://mapit.mysociety.org/area/2223.geojson) <i>(renamed from `2223.geojson`)</i>


### ⚡Dynamic Data

- **Live Power Cut Data**: Northern Powergrid's [OpenDataSoft API](https://northernpowergrid.opendatasoft.com/explore/dataset/live-power-cuts-data/information/)
- **Risk of Flooding from Surface Water Map**: Environment Agency [Web Map Service (WMS)](https://environment.data.gov.uk/dataset/b5aaa28d-6eb9-460e-8d6f-43caa71fbe0e)


### 🧪 Reproducibility

- Live site is currently available at [powergrid.oryley.com](https://powergrid.oryley.com)
- Static Data downloads can be found in [Directory Structure](#-directory-structure)
- To use this visualisation locally, clone this repository, and run using a local test server

```bash
git clone https://github.com/Oscar-Ryley/Flood-Risk-Exposure.git
cd Flood-Risk-Exposure
```


## Citation

**BibTeX:**
```bibtex
@misc{servonat_ryley_2026_floodrisk,
  author       = {Servonat, Isabelle and Ryley, Oscar and Sun, Hongjian and Li, Wenzhu and Alpizar Santana, Misael},
  title        = {Flood Risk Exposure Mapping for Energy Resources in the Durham Area},
  year         = {2026},
  publisher    = {GitHub},
  journal      = {GitHub Repository},
  howpublished = {\url{https://github.com/oscar-ryley/flood-risk-exposure}},
  note         = {EPSRC Vacation Internship Project, Associated with UKRI Grant MR/Z50578X/1}
}
```
