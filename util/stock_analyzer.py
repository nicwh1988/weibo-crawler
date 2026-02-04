#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import logging
import requests
from typing import Dict, Any, Optional
from datetime import datetime
import pytz

logger = logging.getLogger("weibo")


class StockAnalyzer:
    """股票内容识别和推送器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化股票分析器
        
        Args:
            config: 配置字典，包含 stock_config
        """
        self.stock_config = config.get('stock_config', {})
        self.enabled = self.stock_config.get('enabled', False)
        self.api_key = self.stock_config.get('zhipu_api_key')
        self.webhook_url = self.stock_config.get('webhook_url')
        self.model = self.stock_config.get('model', 'glm-4-flash')
        self.max_retries = self.stock_config.get('max_retries', 3)  # API调用失败重试次数
        
        # 添加已推送微博ID集合，防止重复推送
        self.pushed_weibo_ids = set()
        
        if self.enabled:
            logger.info("股票内容识别器初始化完成")
            logger.info(f"模型: {self.model}")
            logger.info(f"推送地址: {self.webhook_url}")
        else:
            logger.info("股票内容识别器未启用")
    
    def is_stock_related(self, text: str) -> tuple[bool, str]:
        """
        判断内容是否与股票相关
        
        Args:
            text: 微博文本内容
            
        Returns:
            (是否股票相关, 分析结果)
        """
        if not self.enabled or not self.api_key:
            return False, ""
        
        # 使用智谱AI的官方API格式
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""请判断以下微博内容是否与股票、证券、投资相关。
如果相关，请简要说明涉及的股票信息（如股票代码、公司名称、投资观点等）；
如果不相关，只回复"不相关"。

微博内容：
{text}

请直接回答，不要有多余的解释。"""
        
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的股票内容识别助手。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,  # 降低温度以获得更确定的结果
            "max_tokens": 500
        }
        
        # 重试机制
        for attempt in range(self.max_retries):
            try:
                # 智谱AI的API endpoint
                response = requests.post(
                    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    analysis = result['choices'][0]['message']['content'].strip()
                    
                    # 判断是否相关
                    is_related = "不相关" not in analysis
                    
                    logger.info(f"股票识别结果: {'相关' if is_related else '不相关'} - {analysis}")
                    return is_related, analysis
                else:
                    logger.error(f"智谱AI API调用失败(第{attempt + 1}次): {response.status_code} - {response.text}")
                    if attempt < self.max_retries - 1:
                        continue
                    return False, ""
                    
            except Exception as e:
                logger.error(f"股票内容识别失败(第{attempt + 1}次): {str(e)}")
                if attempt < self.max_retries - 1:
                    continue
                return False, ""
        
        return False, ""
    
    def push_to_weixin(self, content: str, weibo_data: Dict[str, Any]) -> bool:
        """
        推送内容到企业微信
        
        Args:
            content: AI分析结果（不使用，保留参数兼容性）
            weibo_data: 微博数据
            
        Returns:
            是否推送成功
        """
        if not self.webhook_url:
            logger.warning("未配置企业微信推送地址")
            return False
        
        try:
            # 构建推送消息
            text = weibo_data.get('text', '')
            created_at = weibo_data.get('created_at', '')
            weibo_id = weibo_data.get('id', '')
            user_id = weibo_data.get('user_id', '')
            
            # 转换时间为北京时间格式
            beijing_time_str = ""
            if created_at:
                try:
                    # 解析时间字符串（支持多种格式）
                    if 'T' in created_at:
                        # ISO格式: 2025-12-16T10:00:00
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    elif '+' in created_at or created_at.count(' ') >= 4:
                        # 微博格式: Thu Dec 18 08:33:17 +0800 2025
                        dt = datetime.strptime(created_at, '%a %b %d %H:%M:%S %z %Y')
                    else:
                        # 标准格式: 2025-12-16 10:00:00
                        dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                        # 如果没有时区信息，假定为北京时间
                        beijing_tz = pytz.timezone('Asia/Shanghai')
                        dt = beijing_tz.localize(dt)
                    
                    # 转换为北京时间（东八区）
                    beijing_tz = pytz.timezone('Asia/Shanghai')
                    beijing_time = dt.astimezone(beijing_tz)
                    beijing_time_str = beijing_time.strftime('%Y-%m-%d %H:%M:%S')
                except Exception as e:
                    logger.warning(f"时间转换失败: {e}, 使用原始时间: {created_at}")
                    beijing_time_str = created_at
            
            # 构建微博链接
            weibo_url = f"https://weibo.com/{user_id}/{weibo_id}" if user_id and weibo_id else ""
            
            # 组装消息内容
            message_parts = []
            if beijing_time_str:
                message_parts.append(f"发博时间: {beijing_time_str}")
            message_parts.append(f"\n{text}")
            if weibo_url:
                message_parts.append(f"\n\n链接: {weibo_url}")
            
            message = "".join(message_parts)
            
            # 企业微信webhook格式
            data = {
                "msgtype": "text",
                "text": {
                    "content": message
                }
            }
            
            response = requests.post(
                self.webhook_url,
                headers={"Content-Type": "application/json"},
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    logger.info(f"成功推送股票相关微博到企业微信: {weibo_data.get('id')}")
                    return True
                else:
                    logger.error(f"企业微信推送失败: {result}")
                    return False
            else:
                logger.error(f"企业微信推送失败: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"推送到企业微信失败: {str(e)}")
            return False
    
    def analyze_and_push(self, weibo_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析微博内容并在必要时推送
        
        Args:
            weibo_data: 微博数据字典
            
        Returns:
            添加了股票分析结果的微博数据
        """
        if not self.enabled:
            return weibo_data
        
        text = weibo_data.get('text', '')
        if not text:
            return weibo_data
        
        # 获取微博ID
        weibo_id = weibo_data.get('id')
        
        # 检查是否已经推送过该微博
        if weibo_id and weibo_id in self.pushed_weibo_ids:
            logger.debug(f"微博 {weibo_id} 已经推送过，跳过")
            # 即使跳过推送，也添加分析结果标记
            if 'stock_analysis' not in weibo_data:
                weibo_data['stock_analysis'] = {
                    'is_stock_related': True,
                    'analysis': '(已推送，跳过重复分析)'
                }
            return weibo_data
        
        # 判断是否股票相关
        is_related, analysis = self.is_stock_related(text)
        
        # 添加分析结果到微博数据
        weibo_data['stock_analysis'] = {
            'is_stock_related': is_related,
            'analysis': analysis
        }
        
        # 如果相关，推送到企业微信
        if is_related and weibo_id:
            success = self.push_to_weixin(analysis, weibo_data)
            if success:
                # 推送成功后记录该微博ID
                self.pushed_weibo_ids.add(weibo_id)
                logger.info(f"微博 {weibo_id} 推送成功，已添加到去重列表")
        
        return weibo_data
