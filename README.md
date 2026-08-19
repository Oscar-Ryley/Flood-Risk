# Flood Risk Prioritisation for Grid Assets

> Combining flood, terrain and energy-asset data to map the exposure of, screen, and prioritise substations and distributed energy resources (DERs) in County Durham for further study, supported by a reproducible data and visualisation workflow.

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

[![Live Site Screenshot](public/data/images/screenshot.png)](https://powergrid.oryley.com)


## Data

> ### Initial Sources (not yet used)
> - Renewable: [Renewables.ninja](https://www.renewables.ninja/)
> - Hazard-Energy: [Hazard-Energy Interrelationship Matrix](https://tageleaschale.shinyapps.io/deploy-app-3/)
> - Past Weather Events: [Met Office, Past Weather Events](https://weather.metoffice.gov.uk/learn-about/past-uk-weather-events)
> - NASA Earth Data: [earthdata.nasa.gov](https://www.earthdata.nasa.gov/)


### 📁 Directory Structure

```text
data/
├── images/
├── county_durham.geojson
├── powercut_archive.geojson
├── substation_sites_filtered.csv
└── substation_sites_list.geojson
```

- `substation_sites_list.geojson`: [Northern Power Grid Open Data](https://northernpowergrid.opendatasoft.com/explore/dataset/substation_sites_list/export/?disjunctive.dno_area)
- `substation_sites_filtered.csv`: 
- `county_durham.geojson`: [MapIt Durham County Council Area - ID 2223](https://mapit.mysociety.org/area/2223.geojson) <i>(renamed from `2223.geojson`)</i>
- `powercut_archive.geojson`: Updated every 30 minutes by a GitHub Action that calls Northern Powergrid's [OpenDataSoft API](https://northernpowergrid.opendatasoft.com/explore/dataset/live-power-cuts-data/information/) and flood warnings from [the Environment Agency](https://environment.data.gov.uk/flood-monitoring/id/floods). Each run appends a new line, which is a timestamped GeoJSON snapshot.


### ⚡ Dynamic Data

- **Live Power Cut Data**: Northern Powergrid's [OpenDataSoft API](https://northernpowergrid.opendatasoft.com/explore/dataset/live-power-cuts-data/information/)
- **Risk of Flooding from Surface Water Map**: Environment Agency [Web Map Service (WMS)](https://environment.data.gov.uk/dataset/b5aaa28d-6eb9-460e-8d6f-43caa71fbe0e)


### 🧪 Reproducibility

- Live site is currently available at [powergrid.oryley.com](https://powergrid.oryley.com)
- Static Data downloads can be found in [Directory Structure](#-directory-structure)
- A GitHub Actions workflow is archiving live Northern Power Grid power cut data, with flood warnings, to the repository. To create snapshots locally, run `scripts/archive_powercuts.py` and it will update `data/powercut_archive.geojson`
- To use this visualisation locally, clone this repository, and run using a local test server

```bash
git clone https://github.com/Oscar-Ryley/Flood-Risk.git
cd Flood-Risk
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
  howpublished = {\url{https://github.com/oscar-ryley/flood-risk}},
  note         = {EPSRC Vacation Internship Project, Associated with UKRI Grant MR/Z50578X/1}
}
```
