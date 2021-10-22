# Cell Labeling App

## Running the app

1. Clone the repository to a computer with access to on-prem resources using `git clone`
2. Run the following: 
```
cd cell_labeling_app
conda env create -f environment.yml
conda activate cell_labeling_app
python src/server/app.py --user_id <FirstName.LastName> (in lower case)
```
This step launches a web server listening on port 5000

3. If this computer does not have access to a browser, then you need to tunnel to port `5000` on a computer that does.
On linux the command is 
```
ssh -L 5000:localhost:5000 -N -f -l <username> <domain name of computer in step (1)>
```

4. Go to localhost:5000 in a browser

## Notes

An ROI that you have not labeled before is randomly sampled until there are no more ROIs left to label.

The projection plot starts out centered on the ROI. Double click the plot to zoom out the entire projection, and double click again to return to the original view.
Use the plot tools in the upper right to pan, zoom, etc.

The default video timeframe is `argmax(trace magnitude) +- 300 timesteps`
To change this timeframe, select a timeframe from the trace and then click the "Go to trace timesteps" button.

The video takes about 30 seconds to load.
