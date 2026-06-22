export type PlatformKey = 'xhs' | 'dy' | 'ks' | 'bili' | 'wb' | 'tieba' | 'zhihu' | 'wechat';

export const platformLabels: Record<PlatformKey, string> = {
  xhs: '小红书',
  dy: '抖音',
  ks: '快手',
  bili: 'B 站',
  wb: '微博',
  tieba: '贴吧',
  zhihu: '知乎',
  wechat: '公众号',
};

export interface PlatformOption {
  key: PlatformKey;
  label: string;
  description: string;
  crawlerSupported: boolean;
}

export const platformOptions: PlatformOption[] = [
  { key: 'xhs', label: platformLabels.xhs, description: '图文/视频与评论采集', crawlerSupported: true },
  { key: 'dy', label: platformLabels.dy, description: '视频内容与评论采集', crawlerSupported: true },
  { key: 'bili', label: platformLabels.bili, description: '视频内容与评论采集', crawlerSupported: true },
  { key: 'ks', label: platformLabels.ks, description: '短视频内容与评论采集', crawlerSupported: true },
  { key: 'wb', label: platformLabels.wb, description: '微博内容与评论采集', crawlerSupported: true },
  { key: 'zhihu', label: platformLabels.zhihu, description: '问答/文章与评论采集', crawlerSupported: true },
  { key: 'tieba', label: platformLabels.tieba, description: '帖子与回复采集', crawlerSupported: true },
  { key: 'wechat', label: platformLabels.wechat, description: '需后续接官方接口', crawlerSupported: false },
];
