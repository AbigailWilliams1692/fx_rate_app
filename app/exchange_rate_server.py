from flask import Flask, render_template, request, jsonify, make_response
import requests
import json
from datetime import datetime, timedelta
from flask_cors import CORS
import os
import time
import random

app = Flask(__name__, template_folder='../templates')
CORS(app)  # 允许跨域请求

# 汇率API配置 - 多个可选的API，按优先级排序
EXCHANGE_RATE_APIS = [
    {
        'name': 'ExchangeRate-API',
        'url': 'https://api.exchangerate-api.com/v4/latest/{base}',
        'requires_key': False,
        'rate_limit': 1500,  # 每月免费额度
        'timeout': 10
    },
    {
        'name': 'Frankfurter',
        'url': 'https://api.frankfurter.app/latest?from={base}&to={target}',
        'requires_key': False,
        'rate_limit': 1000,  # 每日免费额度
        'timeout': 10
    },
    {
        'name': 'OpenExchangeRates',
        'url': 'https://open.er-api.com/v6/latest/{base}',
        'requires_key': False,
        'rate_limit': 1500,  # 每月免费额度
        'timeout': 10
    }
]

# 货币数据 - 与前端保持一致的格式
CURRENCY_DATA = {
    "USD": {"name": "United States Dollar", "flag": "🇺🇸"},
    "EUR": {"name": "Euro", "flag": "🇪🇺"},
    "GBP": {"name": "British Pound", "flag": "🇬🇧"},
    "JPY": {"name": "Japanese Yen", "flag": "🇯🇵"},
    "CNY": {"name": "Chinese Yuan", "flag": "🇨🇳"},
    "CAD": {"name": "Canadian Dollar", "flag": "🇨🇦"},
    "AUD": {"name": "Australian Dollar", "flag": "🇦🇺"},
    "CHF": {"name": "Swiss Franc", "flag": "🇨🇭"},
    "HKD": {"name": "Hong Kong Dollar", "flag": "🇭🇰"},
    "SGD": {"name": "Singapore Dollar", "flag": "🇸🇬"},
    "KRW": {"name": "South Korean Won", "flag": "🇰🇷"},
    "INR": {"name": "Indian Rupee", "flag": "🇮🇳"},
    "RUB": {"name": "Russian Ruble", "flag": "🇷🇺"},
    "BRL": {"name": "Brazilian Real", "flag": "🇧🇷"},
    "MXN": {"name": "Mexican Peso", "flag": "🇲🇽"},
    "AED": {"name": "UAE Dirham", "flag": "🇦🇪"},
    "TRY": {"name": "Turkish Lira", "flag": "🇹🇷"},
    "ZAR": {"name": "South African Rand", "flag": "🇿🇦"},
    "SEK": {"name": "Swedish Krona", "flag": "🇸🇪"},
    "NZD": {"name": "New Zealand Dollar", "flag": "🇳🇿"}
}

# 汇率缓存，避免频繁请求API
exchange_rate_cache = {}
CACHE_DURATION = 300  # 5分钟缓存

def get_cached_rate(base_currency, target_currency):
    """从缓存获取汇率"""
    cache_key = f"{base_currency}_{target_currency}"
    if cache_key in exchange_rate_cache:
        cached_data = exchange_rate_cache[cache_key]
        # 检查缓存是否过期
        if datetime.now() - cached_data['timestamp'] < timedelta(seconds=CACHE_DURATION):
            return cached_data['rate'], cached_data['source']
    return None, None

def set_cached_rate(base_currency, target_currency, rate, source):
    """设置汇率缓存"""
    cache_key = f"{base_currency}_{target_currency}"
    exchange_rate_cache[cache_key] = {
        'rate': rate,
        'source': source,
        'timestamp': datetime.now()
    }

def get_exchange_rate_from_api(base_currency, target_currency):
    """从API获取汇率数据，尝试多个API源"""
    errors = []
    
    for api_config in EXCHANGE_RATE_APIS:
        try:
            if api_config['name'] == 'ExchangeRate-API':
                url = api_config['url'].format(base=base_currency)
            elif api_config['name'] == 'Frankfurter':
                url = api_config['url'].format(base=base_currency, target=target_currency)
            elif api_config['name'] == 'OpenExchangeRates':
                url = api_config['url'].format(base=base_currency)
            
            response = requests.get(url, timeout=api_config['timeout'])
            
            if response.status_code == 200:
                data = response.json()
                
                if api_config['name'] == 'ExchangeRate-API':
                    rate = data.get('rates', {}).get(target_currency)
                elif api_config['name'] == 'Frankfurter':
                    rate = data.get('rates', {}).get(target_currency)
                elif api_config['name'] == 'OpenExchangeRates':
                    rate = data.get('rates', {}).get(target_currency)
                
                if rate:
                    print(f"成功从 {api_config['name']} 获取汇率: 1 {base_currency} = {rate} {target_currency}")
                    return {
                        'rate': rate,
                        'date': data.get('date', datetime.now().strftime('%Y-%m-%d')),
                        'source': api_config['name']
                    }
                else:
                    errors.append(f"{api_config['name']}: 未找到汇率数据")
            else:
                errors.append(f"{api_config['name']}: HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            errors.append(f"{api_config['name']}: 请求超时")
        except requests.exceptions.ConnectionError:
            errors.append(f"{api_config['name']}: 连接错误")
        except requests.exceptions.RequestException as e:
            errors.append(f"{api_config['name']}: {str(e)}")
        except json.JSONDecodeError:
            errors.append(f"{api_config['name']}: 响应格式错误")
        except Exception as e:
            errors.append(f"{api_config['name']}: 未知错误 - {str(e)}")
    
    # 如果所有API都失败，返回默认汇率（用于演示）
    if base_currency == "USD" and target_currency == "CNY":
        return {
            'rate': 6.99,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'source': '默认汇率(演示)'
        }
    
    return None

def get_historical_data_from_api(base_currency, target_currency, days=30):
    """从Frankfurter API获取真实历史汇率数据"""
    try:
        # Frankfurter API支持历史数据查询
        # 计算开始和结束日期
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Frankfurter API URL for historical data
        url = f"https://api.frankfurter.app/{start_date.strftime('%Y-%m-%d')}..{end_date.strftime('%Y-%m-%d')}?from={base_currency}&to={target_currency}"
        
        print(f"正在从Frankfurter API获取历史数据: {url}")
        
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        if 'rates' not in data:
            print(f"Frankfurter API响应中没有rates字段: {data}")
            return None
        
        history = []
        
        # Frankfurter API返回的数据格式: {"2023-01-01": {"USD": 1.0, "EUR": 0.85}}
        for date_str, rates in data['rates'].items():
            if target_currency in rates:
                history.append({
                    'date': date_str,
                    'rate': round(rates[target_currency], 4),
                    'timestamp': f"{date_str} 12:00:00"
                })
        
        # 按日期排序
        history.sort(key=lambda x: x['date'])
        
        print(f"成功获取{len(history)}天的历史数据")
        return history
        
    except requests.exceptions.RequestException as e:
        print(f"Frankfurter API请求失败: {e}")
        return None
    except Exception as e:
        print(f"获取历史数据时发生错误: {e}")
        return None

def generate_historical_data(base_currency, target_currency, days=30):
    """获取历史汇率数据 - 优先使用真实API，失败时回退到模拟数据"""
    
    # 首先尝试从真实API获取数据
    real_history = get_historical_data_from_api(base_currency, target_currency, days)
    
    if real_history and len(real_history) > 0:
        return real_history
    
    # 如果真实API失败，回退到模拟数据
    print(f"真实API获取失败，使用模拟数据 for {base_currency}/{target_currency}")
    
    base_rate = 6.99 if base_currency == "USD" and target_currency == "CNY" else random.uniform(0.8, 1.2)
    
    history = []
    today = datetime.now()
    
    for i in range(days, -1, -1):
        date = today - timedelta(days=i)
        # 生成随机但合理的汇率变化
        variation = (random.random() - 0.5) * 0.05
        rate = base_rate + variation
        base_rate = rate  # 更新基础汇率
        
        history.append({
            'date': date.strftime('%Y-%m-%d'),
            'rate': round(rate, 4),
            'timestamp': date.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    return history

@app.route('/')
def index():
    """渲染主页 - 提供Google风格的前端"""
    return render_template('index.html')

@app.route('/api/currencies')
def get_currencies():
    """获取所有支持的货币列表"""
    return jsonify({
        'success': True,
        'currencies': CURRENCY_DATA,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/exchange_rate')
def get_exchange_rate():
    """获取货币对汇率 - 适配Google风格前端"""
    base_currency = request.args.get('base', 'USD').upper()
    target_currency = request.args.get('target', 'CNY').upper()
    
    if base_currency not in CURRENCY_DATA:
        return jsonify({
            'success': False,
            'error': f"不支持的基准货币: {base_currency}",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 400
    
    if target_currency not in CURRENCY_DATA:
        return jsonify({
            'success': False,
            'error': f"不支持的目标货币: {target_currency}",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 400
    
    # 尝试从缓存获取
    cached_rate, cached_source = get_cached_rate(base_currency, target_currency)
    if cached_rate is not None:
        result = {
            "success": True,
            "base_currency": base_currency,
            "target_currency": target_currency,
            "exchange_rate": cached_rate,
            "inverse_rate": 1 / cached_rate if cached_rate != 0 else 0,
            "base_name": CURRENCY_DATA[base_currency]["name"],
            "target_name": CURRENCY_DATA[target_currency]["name"],
            "last_updated": datetime.now().strftime('%Y-%m-%d'),
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "source": cached_source,
            "cached": True
        }
        return jsonify(result)
    
    # 从API获取汇率
    try:
        api_result = get_exchange_rate_from_api(base_currency, target_currency)
        
        if api_result is None:
            return jsonify({
                "success": False,
                "error": "无法从任何汇率API获取数据",
                "suggestions": [
                    "1. 检查网络连接",
                    "2. 等待几分钟后重试",
                    "3. 某些API可能有请求频率限制"
                ],
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }), 503
        
        rate = api_result['rate']
        
        # 缓存结果
        set_cached_rate(base_currency, target_currency, rate, api_result.get('source', '未知'))
        
        result = {
            "success": True,
            "base_currency": base_currency,
            "target_currency": target_currency,
            "exchange_rate": rate,
            "inverse_rate": 1 / rate if rate != 0 else 0,
            "base_name": CURRENCY_DATA[base_currency]["name"],
            "target_name": CURRENCY_DATA[target_currency]["name"],
            "last_updated": api_result.get('date', datetime.now().strftime('%Y-%m-%d')),
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "source": api_result.get('source', '未知'),
            "cached": False
        }
        return jsonify(result)
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"服务器错误: {str(e)}",
            "details": "请稍后重试或检查网络连接",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@app.route('/api/historical')
def get_historical_data():
    """获取历史汇率数据 - 用于图表显示"""
    base_currency = request.args.get('base', 'USD').upper()
    target_currency = request.args.get('target', 'CNY').upper()
    days = request.args.get('days', '30')
    
    try:
        days_int = int(days)
    except ValueError:
        days_int = 30
    
    if base_currency not in CURRENCY_DATA:
        return jsonify({
            'success': False,
            'error': f"不支持的基准货币: {base_currency}",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 400
    
    if target_currency not in CURRENCY_DATA:
        return jsonify({
            'success': False,
            'error': f"不支持的目标货币: {target_currency}",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 400
    
    try:
        # 获取当前汇率作为基准
        current_rate_data = get_exchange_rate_from_api(base_currency, target_currency)
        if current_rate_data is None:
            # 使用默认汇率
            base_rate = 6.99 if base_currency == "USD" and target_currency == "CNY" else 1.0
        else:
            base_rate = current_rate_data['rate']
        
        # 生成历史数据
        history = generate_historical_data(base_currency, target_currency, days_int)
        
        result = {
            "success": True,
            "base_currency": base_currency,
            "target_currency": target_currency,
            "current_rate": base_rate,
            "historical_data": history,
            "days": days_int,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"获取历史数据失败: {str(e)}",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@app.route('/api/convert')
def convert_amount():
    """转换货币金额"""
    base_currency = request.args.get('base', 'USD').upper()
    target_currency = request.args.get('target', 'CNY').upper()
    
    try:
        amount = float(request.args.get('amount', 1.0))
    except ValueError:
        return jsonify({
            "success": False,
            "error": "金额必须为数字",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 400
    
    if amount <= 0:
        return jsonify({
            "success": False,
            "error": "金额必须大于0",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 400
    
    # 获取汇率
    try:
        api_result = get_exchange_rate_from_api(base_currency, target_currency)
        
        if not api_result:
            return jsonify({
                "success": False,
                "error": "无法获取汇率数据",
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }), 503
        
        rate = api_result['rate']
        converted_amount = amount * rate
        
        result = {
            "success": True,
            "amount": amount,
            "converted_amount": converted_amount,
            "base_currency": base_currency,
            "target_currency": target_currency,
            "exchange_rate": rate,
            "base_name": CURRENCY_DATA[base_currency]["name"],
            "target_name": CURRENCY_DATA[target_currency]["name"],
            "formatted": f"{amount:,.2f} {base_currency} = {converted_amount:,.2f} {target_currency}",
            "source": api_result.get('source', '未知'),
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"转换失败: {str(e)}",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@app.route('/api/health')
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "healthy",
        "service": "Exchange Rate API",
        "version": "2.0",
        "timestamp": datetime.now().isoformat(),
        "supported_currencies": len(CURRENCY_DATA),
        "cache_size": len(exchange_rate_cache),
        "active_apis": [api['name'] for api in EXCHANGE_RATE_APIS]
    })

@app.route('/api/clear_cache')
def clear_cache():
    """清除汇率缓存"""
    exchange_rate_cache.clear()
    return jsonify({
        "success": True,
        "message": "汇率缓存已清除",
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.errorhandler(404)
def not_found(error):
    """处理404错误"""
    return jsonify({
        "success": False,
        "error": "请求的资源不存在",
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """处理500错误"""
    return jsonify({
        "success": False,
        "error": "服务器内部错误",
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }), 500

if __name__ == '__main__':
    # 创建templates目录（如果不存在）
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    print("=" * 60)
    print("Google风格汇率查询服务器启动")
    print("=" * 60)
    print("服务器配置:")
    print(f"  端口: 5000")
    print(f"  支持货币: {len(CURRENCY_DATA)} 种")
    print(f"  缓存时长: {CACHE_DURATION} 秒")
    print("=" * 60)
    print("API端点:")
    print("  GET /                    - 主界面 (Google风格)")
    print("  GET /api/exchange_rate   - 获取当前汇率")
    print("  GET /api/historical      - 获取历史汇率数据")
    print("  GET /api/convert         - 转换货币金额")
    print("  GET /api/currencies      - 获取货币列表")
    print("  GET /api/health          - 健康检查")
    print("  GET /api/clear_cache     - 清除缓存")
    print("=" * 60)
    print("支持的汇率API (按优先级顺序):")
    for i, api in enumerate(EXCHANGE_RATE_APIS, 1):
        print(f"  {i}. {api['name']}: {api['url']}")
    print("=" * 60)
    print("默认货币对: USD → CNY")
    print("访问地址: http://127.0.0.1:5000")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
