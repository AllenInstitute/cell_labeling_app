# Cell Labeling App

## Running the app

1. Clone the repository to a computer with access to on-prem resources using `git clone`
2. Run the following: 
```
cd cell_labeling_app
conda env create -f environment.yml
conda activate cell_labeling_app
```

Then install the labeling app with
```
python setup.py install
```

You will need a config file (.py) to run the app. It currently requires the following:

| variable                | description                                                       |
|-------------------------|-------------------------------------------------------------------|
| SQLALCHEMY_DATABASE_URI | Path to app database (will get created if does not already exist) |
| ARTIFACT_DIR            | Path to artifacts (videos, projections, etc) (as hdf5 files)      |
| PREDICTIONS_DIR         | Path to classifier predictions pre-labeling   |
| PORT         | Port to run the app on   |
| DEBUG         | Whether to enable debug mode (extra logging, etc)  |

If you have not already created and populated your `SQLALCHEMY_DATABASE`, execute `python src/server/database/populate_labeling_job.py` to populate your database of labeling jobs.

Execute `python src/server/main.py` to start the web server.

3. If this computer does not have access to a browser, then you need to tunnel to port `<PORT>` on a computer that does.
On linux the command is 
```
ssh -L <PORT>:localhost:<PORT> -N -f -l <username> <domain name of computer in step (1)>
```

4. Go to `localhost:<PORT>` in a browser

## Notes

An ROI that you have not labeled before is randomly sampled until there are no more ROIs left to label.

The projection plot starts out centered on the ROI. Double click the plot to zoom out the entire projection, and double click again to return to the original view.
Use the plot tools in the upper right to pan, zoom, etc.

The default video timeframe is `argmax(trace magnitude) +- 300 timesteps`
To change this timeframe, select a timeframe from the trace and then click the "Go to trace timesteps" button.
