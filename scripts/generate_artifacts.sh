experiment_ids_path=$1
correlation_dir=$2
out_path=$3
conda_env=$4
video_path=$5
roi_path=$6

readarray -t exp_ids < $experiment_ids_path
mkdir -p ${out_path}


for exp_id in ${exp_ids[@]}
  do
    echo ${exp_id}
    $conda_env -m ophys_etl.modules.roi_cell_classifier.compute_artifacts \
      --video_path ${video_path}/${exp_id}_denoised_video.h5 \
      --correlation_path ${correlation_dir}/${exp_id}_correlation_projection.png \
      --roi_path ${roi_path}/${exp_id}_rois.json \
      --artifact_path ${out_path}/${exp_id}_artifacts.h5 \
      --projection_lower_quantile 0.0 \
      --projection_upper_quantile 1.0 &
  done