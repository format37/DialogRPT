import redis
import time
import torch, pdb
import numpy as np
import os
from shared import download_model, EOS_token
from score import get_model

class GPT2Generator:

    def __init__(self, path, cuda):
        from transformers19 import GPT2Tokenizer, GPT2LMHeadModel, GPT2Config
        self.tokenizer = GPT2Tokenizer.from_pretrained('gpt2')
        model_config = GPT2Config(n_embd=1024, n_layer=24, n_head=16)
        self.model = GPT2LMHeadModel(model_config)
        download_model(path)
        print('loading from ' + path)
        weights = torch.load(path)
        if "lm_head.decoder.weight" in weights:
            weights["lm_head.weight"] = weights["lm_head.decoder.weight"]
            weights.pop("lm_head.decoder.weight", None)
        self.model.load_state_dict(weights)
        self.ix_EOS = 50256
        self.model.eval()
        self.cuda = cuda
        if self.cuda:
            self.model.cuda()

    def tokenize(self, cxt):
        turns = cxt.split(EOS_token)
        ids = []
        for turn in turns:
            ids += self.tokenizer.encode(turn.strip()) + [self.ix_EOS]
        ids = torch.tensor([ids]).view(1, -1)
        if self.cuda:
            ids = ids.cuda()
        return ids

    def predict_beam(self, cxt, topk=3, topp=0.8, beam=10, max_t=30):
        """ pick top tokens at each time step """

        tokens = self.tokenize(cxt)
        len_cxt = tokens.shape[1]
        sum_logP = [0]
        finished = []

        for _ in range(max_t):
            outputs = self.model(tokens)
            predictions = outputs[0]
            logP = torch.log_softmax(predictions[:, -1, :], dim=-1)
            next_logP, next_token = torch.topk(logP, topk)
            sumlogP_ij = []
            sum_prob = 0
            for i in range(tokens.shape[0]):
                for j in range(topk):
                    sum_prob += np.exp(logP[i, j].item())
                    if sum_prob > topp:
                        break
                    if next_token[i, j] == self.ix_EOS:
                        seq = torch.cat([tokens[i, len_cxt:], next_token[i, j].view(1)], dim=-1)
                        if self.cuda:
                            seq = seq.cpu()
                        seq = seq.detach().numpy().tolist()
                        prob = np.exp((sum_logP[i] + next_logP[i, j].item()) / len(seq))
                        hyp = self.tokenizer.decode(seq[:-1])  # don't include EOS
                        finished.append((prob, hyp))
                    else:
                        sumlogP_ij.append((
                            sum_logP[i] + next_logP[i, j].item(),
                            i, j))

            if not sumlogP_ij:
                break
            sumlogP_ij = sorted(sumlogP_ij, reverse=True)[:min(len(sumlogP_ij), beam)]
            new_tokens = []
            new_sum_logP = []
            for _sum_logP, i, j in sumlogP_ij:
                new_tokens.append(
                    torch.cat([tokens[i, :], next_token[i, j].view(1)], dim=-1).view(1, -1)
                )
                new_sum_logP.append(_sum_logP)
            tokens = torch.cat(new_tokens, dim=0)
            sum_logP = new_sum_logP

        return finished

    def predict_sampling(self, cxt, temperature=1, n_hyp=5, max_t=30):
        """ sampling tokens based on predicted probability """

        tokens = self.tokenize(cxt)
        tokens = tokens.repeat(n_hyp, 1)
        len_cxt = tokens.shape[1]
        sum_logP = [0] * n_hyp
        live = [True] * n_hyp
        seqs = [[] for _ in range(n_hyp)]
        np.random.seed(2020)
        for _ in range(max_t):
            outputs = self.model(tokens)
            predictions = outputs[0]
            prob = torch.softmax(predictions[:, -1, :] / temperature, dim=-1)
            if self.cuda:
                prob = prob.cpu()
            prob = prob.detach().numpy()
            vocab = prob.shape[-1]
            next_tokens = []
            for i in range(n_hyp):
                next_token = np.random.choice(vocab, p=prob[i, :])
                next_tokens.append(next_token)
                if not live[i]:
                    continue
                sum_logP[i] += np.log(prob[i, next_token])
                seqs[i].append(next_token)
                if next_token == self.ix_EOS:
                    live[i] = False
                    continue
            next_tokens = torch.LongTensor(next_tokens).view(-1, 1)
            if self.cuda:
                next_tokens = next_tokens.cuda()
            tokens = torch.cat([tokens, next_tokens], dim=-1)

        ret = []
        for i in range(n_hyp):
            if live[i]:  # only return hyp that ends with EOS
                continue
            prob = np.exp(sum_logP[i] / (len(seqs[i]) + 1))
            hyp = self.tokenizer.decode(seqs[i][:-1])  # strip EOS
            ret.append((prob, hyp))
        return ret

    def play(self, params):
        while True:

            cxt = input('\nContext:\t')
            if not cxt:
                break
            ret = self.predict(cxt, **params)
            for prob, hyp in sorted(ret, reverse=True):
                print('%.3f\t%s' % (prob, hyp))


class Integrated:
    def __init__(self, generator, ranker):
        self.generator = generator
        self.ranker = ranker

    def predict(self, cxt, wt_ranker, params):
        with torch.no_grad():
            prob_hyp = self.generator.predict(cxt, **params)
        probs = np.array([prob for prob, _ in prob_hyp])
        hyps = [hyp for _, hyp in prob_hyp]
        if wt_ranker > 0:
            scores_ranker = self.ranker.predict(cxt, hyps)
            if isinstance(scores_ranker, dict):
                scores_ranker = scores_ranker['final']
            scores = wt_ranker * scores_ranker + (1 - wt_ranker) * probs
        else:
            scores = probs
        ret = []
        for i in range(len(hyps)):
            ret.append((scores[i], probs[i], scores_ranker[i], hyps[i]))
        ret = sorted(ret, reverse=True)
        return ret

    def play(self, wt_ranker, params, cxt):

        result = ''
        try:

            ret = self.predict(cxt, wt_ranker, params)

            for final, prob_gen, score_ranker, hyp in ret:
                print('%.3f gen %.3f ranker %.3f\t%s' % (final, prob_gen, score_ranker, hyp))
                result += str(hyp)
        except Exception as e:
            print("Error: " + str(e))
        return result

# generator init ++
args_path_generator = 'restore/medium_ft.pkl'
args_path_ranker = 'restore/updown.pth'

cuda = False if os.environ['computing'].lower() == 'cpu' else torch.cuda.is_available()
args_sampling = True if os.environ['sampling'].lower() == 'true' else False
args_temperature = float(os.environ['temperature'])
args_n_hyp = int(os.environ['n_hyp'])
args_topk = int(os.environ['topk'])
args_beam = int(os.environ['beam'])
args_topp = float(os.environ['topp'])
args_wt_ranker = float(os.environ['wt_ranker'])

generator = GPT2Generator(args_path_generator, cuda)
if args_sampling:
    params = {'temperature': args_temperature, 'n_hyp': args_n_hyp}
    generator.predict = generator.predict_sampling
else:
    params = {'topk': args_topk, 'beam': args_beam, 'topp': args_topp}
    generator.predict = generator.predict_beam

ranker = get_model(args_path_ranker, cuda)
model = Integrated(generator, ranker)
# generator init --

# wait for request
subscriber = redis.StrictRedis(host='localhost', port=int(os.environ['port']))
publisher = redis.StrictRedis(host='localhost', port=int(os.environ['port']))
pub = publisher.pubsub()
sub = subscriber.pubsub()
sub.subscribe('dialog_en_server')
print('listening..')
while True:
    # receive
    while True:
        message = sub.get_message()
        if message and message['type'] != 'subscribe':
            incoming_text = message['data'].decode("utf-8")
            print('received', incoming_text)
            break
        time.sleep(0.1)

    # generate
    print('generating on:', incoming_text)
    result = model.play(args_wt_ranker, params, incoming_text)
    #result = 'fake result'
    print('sending:', result)
    # send
    publisher.publish("dialog_en_client", result)
    print('listening..')