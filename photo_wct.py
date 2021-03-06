"""
Copyright (C) 2018 NVIDIA Corporation.  All rights reserved.
Licensed under the CC BY-NC-SA 4.0 license (https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode).
"""
from models import *
import torch
import torch.nn as nn
from torch.utils.serialization import load_lua
import numpy as np
import cv2

class PhotoWCT(nn.Module):
  def __init__(self, args):
    super(PhotoWCT, self).__init__()
    # TODO: convert these torch models to pytorch models.
    vgg1 = load_lua(args.vgg1)
    decoder1_torch = load_lua(args.decoder1)
    vgg2 = load_lua(args.vgg2)
    decoder2_torch = load_lua(args.decoder2)
    vgg3 = load_lua(args.vgg3)
    decoder3_torch = load_lua(args.decoder3)
    vgg4 = load_lua(args.vgg4)
    decoder4_torch = load_lua(args.decoder4)
    self.e1 = VGGEncoder1(vgg1)
    self.d1 = VGGDecoder1(decoder1_torch)
    self.e2 = VGGEncoder2(vgg2)
    self.d2 = VGGDecoder2(decoder2_torch)
    self.e3 = VGGEncoder3(vgg3)
    self.d3 = VGGDecoder3(decoder3_torch)
    self.e4 = VGGEncoder4(vgg4)
    self.d4 = VGGDecoder4(decoder4_torch)

  def transform(self, cont_img, styl_img, cont_seg, styl_seg):
    self.__compute_label_info(cont_seg, styl_seg)

    sF4,sF3,sF2,sF1 = self.e4.forward_multiple(styl_img)

    cF4,cpool_idx,cpool1,cpool_idx2,cpool2,cpool_idx3,cpool3 = self.e4(cont_img)
    sF4 = sF4.data.squeeze(0)
    cF4 = cF4.data.squeeze(0)
    csF4 = self.__feature_wct(cF4, sF4, cont_seg, styl_seg)
    Im4 = self.d4(csF4,cpool_idx,cpool1,cpool_idx2,cpool2,cpool_idx3,cpool3)

    cF3,cpool_idx,cpool1,cpool_idx2,cpool2 = self.e3(Im4)
    sF3 = sF3.data.squeeze(0)
    cF3 = cF3.data.squeeze(0)
    csF3 = self.__feature_wct(cF3, sF3, cont_seg, styl_seg)
    Im3 = self.d3(csF3,cpool_idx,cpool1,cpool_idx2,cpool2)

    cF2,cpool_idx,cpool = self.e2(Im3)
    sF2 = sF2.data.squeeze(0)
    cF2 = cF2.data.squeeze(0)
    csF2 = self.__feature_wct(cF2, sF2, cont_seg, styl_seg)
    Im2 = self.d2(csF2,cpool_idx,cpool)

    cF1 = self.e1(Im2)
    sF1 = sF1.data.squeeze(0)
    cF1 = cF1.data.squeeze(0)
    csF1 = self.__feature_wct(cF1, sF1, cont_seg, styl_seg)
    Im1 = self.d1(csF1)
    return Im1

  # def transform(self, cont_img, styl_img, cont_seg, styl_seg):
  #   self.__compute_label_info(cont_seg, styl_seg)
  #
  #   cF4,cpool_idx,cpool1,cpool_idx2,cpool2,cpool_idx3,cpool3 = self.e4(cont_img)
  #   sF4,spool_idx,spool1,spool_idx2,spool2,spool_idx3,spool3 = self.e4(styl_img)
  #   sF4 = sF4.data.squeeze(0)
  #   cF4 = cF4.data.squeeze(0)
  #   csF4 = self.__feature_wct(cF4, sF4, cont_seg, styl_seg)
  #   Im4 = self.d4(csF4,cpool_idx,cpool1,cpool_idx2,cpool2,cpool_idx3,cpool3)
  #
  #   sF3,spool_idx,spool1,spool_idx2,spool2 = self.e3(styl_img)
  #   cF3,cpool_idx,cpool1,cpool_idx2,cpool2 = self.e3(Im4)
  #   sF3 = sF3.data.squeeze(0)
  #   cF3 = cF3.data.squeeze(0)
  #   csF3 = self.__feature_wct(cF3, sF3, cont_seg, styl_seg)
  #   Im3 = self.d3(csF3,cpool_idx,cpool1,cpool_idx2,cpool2)
  #
  #   sF2,spool_idx,spool= self.e2(styl_img)
  #   cF2,cpool_idx,cpool = self.e2(Im3)
  #   sF2 = sF2.data.squeeze(0)
  #   cF2 = cF2.data.squeeze(0)
  #   csF2 = self.__feature_wct(cF2, sF2, cont_seg, styl_seg)
  #   Im2 = self.d2(csF2,cpool_idx,cpool)
  #
  #   sF1 = self.e1(styl_img)
  #   cF1 = self.e1(Im2)
  #   sF1 = sF1.data.squeeze(0)
  #   cF1 = cF1.data.squeeze(0)
  #   csF1 = self.__feature_wct(cF1, sF1, cont_seg, styl_seg)
  #   Im1 = self.d1(csF1)
  #   return Im1

  def __compute_label_info(self, cont_seg, styl_seg):
    if cont_seg.size == False or styl_seg.size == False:
      return
    max_label = np.max(cont_seg)+1
    self.label_set = np.unique(cont_seg)
    self.label_indicator = np.zeros(max_label)
    for l in self.label_set:
      # if l==0:
      #   continue
      o_cont_mask = np.where(cont_seg.reshape(cont_seg.shape[0] * cont_seg.shape[1]) == l)
      o_styl_mask = np.where(styl_seg.reshape(styl_seg.shape[0] * styl_seg.shape[1]) == l)
      if o_cont_mask[0].size <= 10 or o_styl_mask[0].size <= 10 or \
        self.__large_dff(o_cont_mask[0].size, o_styl_mask[0].size):
        continue
      self.label_indicator[l] = 1

  def __feature_wct(self, cont_feat, styl_feat, cont_seg, styl_seg):
    cont_c, cont_h, cont_w = cont_feat.size(0),cont_feat.size(1),cont_feat.size(2)
    styl_c, styl_h, styl_w = styl_feat.size(0),styl_feat.size(1),styl_feat.size(2)
    cont_feat_view = cont_feat.view(cont_c, -1).clone()
    styl_feat_view = styl_feat.view(styl_c, -1).clone()
    target_feature = cont_feat.view(cont_c, -1).clone()

    if cont_seg.size == False or styl_seg.size == False:
      tmp_target_feature = self.__wct_core(cont_feat_view, styl_feat_view)
      target_feature = tmp_target_feature.view_as(cont_feat)
      ccsF = target_feature.float().unsqueeze(0)
      return torch.autograd.Variable(ccsF)

    t_cont_seg = cv2.resize(cont_seg, (cont_w, cont_h), interpolation = cv2.INTER_NEAREST)
    t_styl_seg = cv2.resize(styl_seg, (styl_w, styl_h), interpolation = cv2.INTER_NEAREST)

    for l in self.label_set:
      if self.label_indicator[l]==0:
        continue;
      cont_mask = np.where(t_cont_seg.reshape(t_cont_seg.shape[0] * t_cont_seg.shape[1]) == l)
      styl_mask = np.where(t_styl_seg.reshape(t_styl_seg.shape[0] * t_styl_seg.shape[1]) == l)
      if cont_mask[0].size <= 0 or styl_mask[0].size <= 0 :
        continue
      cont_indi = torch.LongTensor(cont_mask[0]).cuda(0)
      styl_indi = torch.LongTensor(styl_mask[0]).cuda(0)
      cFFG = torch.index_select(cont_feat_view, 1, cont_indi)
      sFFG = torch.index_select(styl_feat_view, 1, styl_indi)
      tmp_target_feature = self.__wct_core(cFFG, sFFG)
      target_feature.index_copy_(1, cont_indi, tmp_target_feature)

    target_feature = target_feature.view_as(cont_feat)
    ccsF = target_feature.float().unsqueeze(0)
    return torch.autograd.Variable(ccsF)

  def __wct_core(self, cont_feat, styl_feat):
    cFSize = cont_feat.size()
    c_mean = torch.mean(cont_feat, 1)  # c x (h x w)
    c_mean = c_mean.expand_as(cont_feat)
    cont_feat = cont_feat - c_mean

    iden = torch.eye(cFSize[0]).cuda()#.double()
    contentConv = torch.mm(cont_feat, cont_feat.t()).div(cFSize[1] - 1) + iden
    # del iden
    c_u, c_e, c_v = torch.svd(contentConv, some=False)
    # c_e2, c_v = torch.eig(contentConv, True)
    # c_e = c_e2[:,0]

    k_c = cFSize[0]
    for i in range(cFSize[0]-1,-1,-1):
      if c_e[i] >= 0.00001:
        k_c = i+1
        break

    sFSize = styl_feat.size()
    s_mean = torch.mean(styl_feat, 1)
    styl_feat = styl_feat - s_mean.expand_as(styl_feat)
    styleConv = torch.mm(styl_feat, styl_feat.t()).div(sFSize[1] - 1)
    s_u, s_e, s_v = torch.svd(styleConv, some=False)

    k_s = sFSize[0]
    for i in range(sFSize[0]-1,-1,-1):
      if s_e[i] >= 0.00001:
        k_s = i+1
        break

    c_d = (c_e[0:k_c]).pow(-0.5)
    step1 = torch.mm(c_v[:, 0:k_c], torch.diag(c_d))
    step2 = torch.mm(step1, (c_v[:, 0:k_c].t()))
    whiten_cF = torch.mm(step2, cont_feat)

    s_d = (s_e[0:k_s]).pow(0.5)
    targetFeature = torch.mm(torch.mm(torch.mm(s_v[:, 0:k_s], torch.diag(s_d)), (s_v[:, 0:k_s].t())), whiten_cF)
    targetFeature = targetFeature + s_mean.expand_as(targetFeature)
    return targetFeature

  def __large_dff(self, a, b):
    if (a / b >= 100):
      return True
    if (b / a >= 100):
      return True
    return False