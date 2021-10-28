experiment_ids_path=$1
correlation_dir=$2
out_path=$3
conda_env=/allen/aibs/informatics/aamster/miniconda3/envs/cell_labeling_app/bin/python
video_path=/allen/programs/braintv/workgroups/nc-ophys/danielk/deepinterpolation/experiments
roi_path=/allen/aibs/informatics/danielsf/suite2p_210921/v0.10.2/th_3/production

readarray -t exp_ids < $experiment_ids_path
mkdir -p ${out_path}


for exp_id in ${exp_ids[@]}
  do
    echo ${exp_id}
    $conda_env -m ophys_etl.modules.roi_cell_classifier.compute_artifacts \
      --video_path ${video_path}/ophys_experiment_${exp_id}/denoised.h5 \
      --correlation_path ${correlation_dir}/${exp_id}_correlation_proj.png \
      --roi_path ${roi_path}/${exp_id}_suite2p_rois.json \
      --artifact_path ${out_path}/${exp_id}_artifacts.h5 &
  done