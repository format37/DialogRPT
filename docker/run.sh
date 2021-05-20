#docker run --name rudialogrpt --net=host -p 8084:8084 -d format37/dialogrpt:latest
#docker run --name rudialogrpt --net=host -p 6379:6379 -d format37/dialogrpt:latest
#docker run --name rudialogrpt --net=bridge -p 6379:6379 -d format37/dialogrpt:latest
#sudo docker run --name dialog_gpt_en --net=host --gpus all -d format37/dialog_gpt_en:latest
sudo docker run --name dialog_gpt_en --gpus all --net=host -e "computing=gpu" -e "port=6379" -e "sampling=true" -e "temperature=0.5" -e "n_hyp=1" -e "topk=3" -e "beam=3" -e "topp=0.8" -e "wt_ranker=1." -d format37/dialog_gpt_en:latest
