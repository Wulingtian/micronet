import sys
sys.path.append("..")
import torch.nn as nn
from quantize import ActivationBin

# 通道混合
def channel_shuffle(x, groups):
    """shuffle channels of a 4-D Tensor"""
    batch_size, channels, height, width = x.size()
    assert channels % groups == 0
    channels_per_group = channels // groups
    # split into groups
    x = x.view(batch_size, groups, channels_per_group, height, width)
    # transpose 1, 2 axis
    x = x.transpose(1, 2).contiguous()
    # reshape into orignal
    x = x.view(batch_size, channels, height, width)
    return x

# *********************量化(三值、二值)卷积*********************
class TnnBinConvBNReLU(nn.Module):
    # 参数：groups-卷积分组数、channel_shuffle-通道混合标志、shuffle_groups-通道混合数（本层需与上一层分组数保持一致）、last_bin-尾层卷积输入二值
    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size,
                 stride=1,
                 padding=0,
                 dilation=1,
                 groups=1,
                 bias=True,
                 padding_mode='zeros',
                 momentum=0.1,
                 channel_shuffle=0,
                 shuffle_groups=1,
                 last_bin=0):
        super(TnnBinConvBNReLU, self).__init__()
        self.channel_shuffle_flag = channel_shuffle
        self.shuffle_groups = shuffle_groups
        self.last_bin = last_bin

        self.tnn_bin_conv = nn.Conv2d(in_channels, out_channels,
                                      kernel_size, stride=stride, padding=padding, dilation=dilation, groups=groups, bias=bias, padding_mode=padding_mode)
        self.bn = nn.BatchNorm2d(out_channels, momentum=momentum)
        self.relu = nn.ReLU(inplace=True)
        self.activation_bin = ActivationBin(A=2)
    
    def forward(self, x):
        x = self.activation_bin(x)
        if self.channel_shuffle_flag:
            x = channel_shuffle(x, groups=self.shuffle_groups)
        x = self.tnn_bin_conv(x)
        x = self.bn(x)
        if self.last_bin:
            x = self.activation_bin(x)
        return x

class Net(nn.Module):
    def __init__(self, cfg = None, A=2):
        super(Net, self).__init__()
        if cfg is None:
            # 模型结构
            cfg = [256, 256, 256, 512, 512, 512, 1024, 1024]
        self.tnn_bin_model = nn.Sequential(
            nn.Conv2d(3, cfg[0], kernel_size=5, stride=1, padding=2),
            nn.BatchNorm2d(cfg[0]),
            TnnBinConvBNReLU(cfg[0], cfg[1], kernel_size=1, stride=1, padding=0, groups=2, channel_shuffle=0),
            TnnBinConvBNReLU(cfg[1], cfg[2], kernel_size=1, stride=1, padding=0, groups=2, channel_shuffle=1, shuffle_groups=2),
            nn.MaxPool2d(kernel_size=2, stride=2, padding=0),

            TnnBinConvBNReLU(cfg[2], cfg[3], kernel_size=3, stride=1, padding=1, groups=16, channel_shuffle=1, shuffle_groups=2),
            TnnBinConvBNReLU(cfg[3], cfg[4], kernel_size=1, stride=1, padding=0, groups=4, channel_shuffle=1, shuffle_groups=16),
            TnnBinConvBNReLU(cfg[4], cfg[5], kernel_size=1, stride=1, padding=0, groups=4, channel_shuffle=1, shuffle_groups=4),
            nn.MaxPool2d(kernel_size=2, stride=2, padding=0),

            TnnBinConvBNReLU(cfg[5], cfg[6], kernel_size=3, stride=1, padding=1, groups=32, channel_shuffle=1, shuffle_groups=4),
            TnnBinConvBNReLU(cfg[6], cfg[7], kernel_size=1, stride=1, padding=0, groups=8, channel_shuffle=1, shuffle_groups=32, last_bin=1),
            nn.Conv2d(cfg[7],  10, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(10),
            nn.ReLU(inplace=True),
            nn.AvgPool2d(kernel_size=8, stride=1, padding=0),
        )

    def forward(self, x):
        x = self.tnn_bin_model(x)
        x = x.view(x.size(0), -1)
        return x
