from os import path as osp

import torch
torch.backends.cudnn.enabled = False
import numpy as np
import torch.nn.functional as F
from datasets.utils import find_dataset_using_name
import hydra
from torch_geometric.utils import intersection_and_union as i_and_u
from models.KPConv.nn import PartSegmentation

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

def train(model, train_loader,optimizer):
    model.train()

    total_loss = correct_nodes = total_nodes = 0
    for i, data in enumerate(train_loader):
        data = data.to(DEVICE)
        optimizer.zero_grad()
        out = model(data)
        loss = F.nll_loss(out, data.y)
        loss.backward()
        #import pdb; pdb.set_trace()
        optimizer.step()
        total_loss += loss.item()
        correct_nodes += out.max(dim=1)[1].eq(data.y).sum().item()
        total_nodes += data.num_nodes

        if (i + 1) % 10 == 0:
            print('[{}/{}] Loss: {:.4f}, Train Accuracy: {:.4f}'.format(
                i + 1, len(train_loader), total_loss / 10,
                correct_nodes / total_nodes))
            total_loss = correct_nodes = total_nodes = 0


def test(model, loader, num_classes):
    model.eval()

    correct_nodes = total_nodes = 0
    intersections, unions, categories = [], [], []
    for data in loader:
        data = data.to(DEVICE)
        with torch.no_grad():
            out = model(data)
        pred = out.max(dim=1)[1]
        correct_nodes += pred.eq(data.y).sum().item()
        total_nodes += data.num_nodes
        i, u = i_and_u(pred, data.y, num_classes, data.batch)
        intersections.append(i.to(DEVICE))
        unions.append(u.to(DEVICE))
        categories.append(data.category.to(DEVICE))

    category = torch.cat(categories, dim=0)
    intersection = torch.cat(intersections, dim=0)
    union = torch.cat(unions, dim=0)

    ious = [[] for _ in range(len(loader.dataset.categories))]
    for j in range(len(loader.dataset)):
        i = intersection[j, loader.dataset.y_mask[category[j]]]
        u = union[j, loader.dataset.y_mask[category[j]]]
        iou = i.to(torch.float) / u.to(torch.float)
        iou[torch.isnan(iou)] = 1
        ious[category[j]].append(iou.mean().item())

    for cat in range(len(loader.dataset.categories)):
        ious[cat] = torch.tensor(ious[cat]).mean().item()

    return correct_nodes / total_nodes, torch.tensor(ious).mean().item()



@hydra.main(config_path='config.yaml')
def main(cfg):
    dataset = find_dataset_using_name(cfg.data.name)(cfg.data)
    model = PartSegmentation(cfg.model.KP_Conv, dataset.num_classes).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    train_loader = dataset.train_dataloader()
    test_loader = dataset.test_dataloader()
    for epoch in range(1, 31):
        train(model, train_loader,optimizer)
        acc, iou = test(model, test_loader, dataset.num_classes)
        print('Epoch: {:02d}, Acc: {:.4f}, IoU: {:.4f}'.format(epoch, acc, iou))

if __name__ == "__main__":
    main()