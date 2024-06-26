# coding:utf8
# 第十周的作业老师答案
import torch
import torch.nn as nn
import numpy as np
import math
import random
import os
import re
from transformers import BertTokenizer, BertModel
import json
from torch.utils.data import DataLoader,Dataset



"""
基于pytorch的LSTM语言模型
"""


class LanguageModel(nn.Module):
    def __init__(self, hidden_size, vocab_size, pretrain_model_path):
        super(LanguageModel, self).__init__()
        self.bert = BertModel.from_pretrained(pretrain_model_path,return_dict=False)
        self.classify = nn.Linear(hidden_size, vocab_size)
        self.loss = nn.CrossEntropyLoss(ignore_index=-1)

    # 当输入真实标签，返回loss值；无真实标签，返回预测值
    def forward(self, x,mask=None, y=None):
        if y is not None:
            x, _ = self.bert(x, attention_mask=mask)
            y_pre= self.classify(x)  # output shape:(batch_size, vocab_size)
            return self.loss(y_pre.view(-1, y_pre.shape[-1]), y.view(-1))
        else:
            # 预测时，可以不使用mask
            x, _ = self.bert(x)
            y_pre = self.classify(x)  # output shape:(batch_size, vocab_size)
            return torch.softmax(y_pre, dim=-1)

def load_corpus(path):
    corpus = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = json.loads(line.strip())
            corpus.append([line["title"],line["content"]])
    return corpus

# 随机生成一个样本
# 从文本中截取随机窗口，前n个字作为输入，最后一个字作为输出
def build_sample(tokenizer, window_size, corpus):
    start = random.randint(0, len(corpus) - 1 - window_size)
    end = start + window_size
    window = corpus[start:end]
    target = corpus[start + 1:end + 1]  # 输入输出错开一位

    x = tokenizer.encode(window, add_special_tokens=False, padding='max_length', truncation=True,
                         max_length=10)  # 将字转换成序号
    y = tokenizer.encode(target, add_special_tokens=False, padding='max_length', truncation=True, max_length=10)

    return x, y



def create_mask(s1, s2):
    len_s1 = s1 + 2 #cls + sep
    len_s2 = s2 + 1 #sep
    # 创建掩码张量
    mask = torch.ones(len_s1 + len_s2, len_s1 + len_s2)
    # print(mask)
    # 遍历s1的每个token
    for i in range(len_s1):
        # s1的当前token不能看到s2的任何token
        mask[i, len_s1:] = 0
    # 遍历s2的每个token
    # print(mask)
    for i in range(len_s2):
        # s2的当前token不能看到后面的s2 token
        mask[len_s1 + i, len_s1 + i + 1:] = 0
    return mask

def pad_mask(tensor, target_shape):
    # 获取输入张量和目标形状的长宽
    height, width = tensor.shape
    target_height, target_width = target_shape
    # 创建一个全零张量,形状为目标形状
    result = torch.zeros(target_shape, dtype=tensor.dtype, device=tensor.device)
    # 计算需要填充或截断的区域
    h_start = 0
    w_start = 0
    h_end = min(height, target_height)
    w_end = min(width, target_width)
    # 将原始张量对应的部分填充到全零张量中
    result[h_start:h_end, w_start:w_end] = tensor[:h_end - h_start, :w_end - w_start]
    return result

# 建立数据集
def build_dataset(tokenizer, corpus, max_length,batch_size):
    dataset = []
    for text in corpus:
        prompt,answer=text[0],text[1]
        # len(prompt)
        prompt_encode=tokenizer.encode(prompt, add_special_tokens=False)
        answer_encode=tokenizer.encode(answer, add_special_tokens=False)
        x = [tokenizer.cls_token_id] + prompt_encode + [tokenizer.sep_token_id] + answer_encode + [
            tokenizer.sep_token_id]
        y = len(prompt_encode) * [-1] + [-1] + answer_encode + [tokenizer.sep_token_id] + [-1]
        # 构建一个的mask矩阵，让prompt内可以交互，answer中上下文之间没有交互
        mask = create_mask(len(prompt_encode), len(answer_encode))
        # padding
        x = x[:max_length] + [0] * (max_length - len(x))
        y = y[:max_length] + [0] * (max_length - len(y))
        x = torch.LongTensor(x)
        y = torch.LongTensor(y)
        mask = pad_mask(mask, (max_length, max_length))
        dataset.append([x, mask, y])
    return DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0)

# 文本生成测试代码
def generate_sentence(openings, model, tokenizer):
    model.eval()
    openings = tokenizer.encode(openings)
    with torch.no_grad():
        while len(openings) <= 40:
            x = torch.LongTensor([openings])
            if torch.cuda.is_available():
                x = x.cuda()
            y = model(x)[0][-1]  # 模型预测的最后一个字
            index = sampling_strategy(y)
            openings.append(index)
    return tokenizer.decode(openings)

def sampling_strategy(prob_distribution):
    if random.random() > 0.1:
        strategy = "greedy"
    else:
        strategy = "sampling"
    if strategy == "greedy":
        return int(torch.argmax(prob_distribution))
    elif strategy == "sampling":
        prob_distribution = prob_distribution.cpu().numpy()
        return np.random.choice(list(range(len(prob_distribution))), p=prob_distribution)


def train(save_weight=True):
    pretrain_model_path = r"E:\Pycharm_learn\pythonProject1\wk6\bert-base-chinese"
    tokenizer = BertTokenizer.from_pretrained(pretrain_model_path)
    vocab_size=tokenizer.vocab_size
    epoch_num = 20  # 训练轮数
    batch_size = 32  # 每次训练样本个数
    char_dim = 768  # 每个字的维度
    max_length= 40
    learning_rate = 0.0005  # 学习率
    corpus_path=r'E:\Pycharm_learn\pythonProject1\wk11\sample_data.json'
    corpus = load_corpus(corpus_path)  # 加载语料
    train_data = build_dataset(tokenizer, corpus, max_length, batch_size)  # 建立数据集

    model = LanguageModel(char_dim,vocab_size, pretrain_model_path)  # 建立模型
    # hidden_size, vocab_size, pretrain_model_path)
    optim = torch.optim.Adam(model.parameters(), lr=learning_rate)  # 建立优化器

    print("文本词表模型加载完毕，开始训练")
    for epoch in range(epoch_num):
        model.train()
        watch_loss = []
        for x,mask,y in train_data:
            loss=model.forward(x,mask,y)  # 计算loss
            loss.backward()  # 梯度下降
            optim.step()     # 更新权重
            optim.zero_grad()  # 梯度归0
            watch_loss.append(loss.item())
        print("=========\n第%d轮平均loss:%f" % (epoch + 1, np.mean(watch_loss)))
        print(generate_sentence("卫生计生委国际司司长：真正的免费医疗不存在", model, tokenizer))
        print(generate_sentence("西安一建筑工地脚手架坍塌 已致5人死亡", model, tokenizer))
    if not save_weight:
        return
    else:
        model_path = r"E:\Pycharm_learn\pythonProject1\wk11\model"
        torch.save(model.state_dict(), model_path)
        return


if __name__ == "__main__":
    # build_vocab_from_corpus("corpus/all.txt")
    train(False)