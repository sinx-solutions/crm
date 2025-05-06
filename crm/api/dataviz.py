import frappe
import random
import json
import datetime
from frappe.utils import now_datetime, add_days, get_datetime
import numpy as np

@frappe.whitelist(allow_guest=True)
def get_sales_forecast():
    """
    Generate a simulated sales forecast with machine learning-like predictions
    """
    # Generate some random historical data
    today = get_datetime(now_datetime())
    dates = [(add_days(today, -i)).strftime("%Y-%m-%d") for i in range(30, 0, -1)]
    
    # Create some realistic sales data with weekly patterns
    base_sales = 1000
    weekly_pattern = [1.2, 1.0, 0.9, 0.8, 1.1, 1.5, 0.7]  # Mon-Sun pattern
    
    historical_data = []
    for i, date in enumerate(dates):
        day_of_week = get_datetime(date).weekday()
        pattern_factor = weekly_pattern[day_of_week]
        
        # Add some randomness and a slight upward trend
        trend_factor = 1 + (i * 0.005)
        random_factor = random.uniform(0.85, 1.15)
        
        sales = base_sales * pattern_factor * trend_factor * random_factor
        historical_data.append({
            "date": date,
            "sales": round(sales, 2),
            "actual": True
        })
    
    # Generate forecast data
    future_dates = [(add_days(today, i)).strftime("%Y-%m-%d") for i in range(1, 15)]
    
    # Simple "ML" forecast - use historical patterns with added uncertainty
    forecast_data = []
    for i, date in enumerate(future_dates):
        day_of_week = get_datetime(date).weekday()
        pattern_factor = weekly_pattern[day_of_week]
        
        # Calculate trend from historical data
        historical_avg = sum(item["sales"] for item in historical_data) / len(historical_data)
        recent_avg = sum(item["sales"] for item in historical_data[-7:]) / 7
        trend_direction = recent_avg / historical_avg
        
        # Forecast with increasing uncertainty
        uncertainty = 1 + (i * 0.02)
        forecast = base_sales * pattern_factor * trend_direction * uncertainty
        
        # Calculate confidence intervals
        lower_bound = forecast * (1 - (0.05 * (i+1)))
        upper_bound = forecast * (1 + (0.05 * (i+1)))
        
        forecast_data.append({
            "date": date,
            "sales": round(forecast, 2),
            "lower_bound": round(lower_bound, 2),
            "upper_bound": round(upper_bound, 2),
            "actual": False
        })
    
    # Generate insights
    weekly_total = sum(item["sales"] for item in historical_data[-7:])
    previous_weekly_total = sum(item["sales"] for item in historical_data[-14:-7])
    week_over_week_change = (weekly_total - previous_weekly_total) / previous_weekly_total * 100
    
    best_day = max(historical_data[-30:], key=lambda x: x["sales"])
    worst_day = min(historical_data[-30:], key=lambda x: x["sales"])
    
    # Calculate seasonality using FFT
    sales_values = [item["sales"] for item in historical_data]
    fft_values = np.abs(np.fft.rfft(sales_values))
    frequencies = np.fft.rfftfreq(len(sales_values))
    
    # Find dominant frequencies (excluding DC component)
    dominant_idx = np.argsort(fft_values[1:])[-3:] + 1
    dominant_periods = [round(1/frequencies[idx]) if frequencies[idx] > 0 else 0 for idx in dominant_idx]
    
    # Filter out invalid periods
    valid_periods = [p for p in dominant_periods if 0 < p <= len(sales_values)]
    seasonality = "Weekly" if 7 in valid_periods or 6 in valid_periods or 8 in valid_periods else "No clear pattern"
    
    # Projected monthly revenue
    projected_monthly = sum(item["sales"] for item in forecast_data[:min(len(forecast_data), 30)])
    
    insights = {
        "week_over_week_change": round(week_over_week_change, 2),
        "best_day": {
            "date": best_day["date"],
            "sales": round(best_day["sales"], 2)
        },
        "worst_day": {
            "date": worst_day["date"],
            "sales": round(worst_day["sales"], 2)
        },
        "seasonality": seasonality,
        "projected_monthly_revenue": round(projected_monthly, 2),
        "confidence_score": random.randint(70, 95)
    }
    
    # Generate some recommendations based on the data
    recommendations = []
    
    if week_over_week_change < 0:
        recommendations.append({
            "type": "warning",
            "message": "Sales are down {0}% week-over-week. Consider launching a promotion.".format(abs(round(week_over_week_change, 1)))
        })
    else:
        recommendations.append({
            "type": "success",
            "message": "Sales are up {0}% week-over-week. Great job!".format(round(week_over_week_change, 1))
        })
    
    # Day of week recommendation
    best_day_name = get_datetime(best_day["date"]).strftime("%A")
    worst_day_name = get_datetime(worst_day["date"]).strftime("%A")
    
    recommendations.append({
        "type": "info",
        "message": "{0} is typically your best performing day. Consider allocating more resources.".format(best_day_name)
    })
    
    recommendations.append({
        "type": "info",
        "message": "{0} is typically your worst performing day. Consider special promotions.".format(worst_day_name)
    })
    
    # Return combined data
    return {
        "historical_data": historical_data,
        "forecast_data": forecast_data,
        "insights": insights,
        "recommendations": recommendations
    }

@frappe.whitelist(allow_guest=True)
def get_customer_segments():
    """
    Generate simulated customer segmentation data
    """
    segments = [
        {"name": "High Value", "count": random.randint(50, 150), "avg_revenue": random.uniform(5000, 10000)},
        {"name": "Regular", "count": random.randint(500, 1500), "avg_revenue": random.uniform(1000, 3000)},
        {"name": "Occasional", "count": random.randint(2000, 5000), "avg_revenue": random.uniform(200, 800)},
        {"name": "New", "count": random.randint(100, 400), "avg_revenue": random.uniform(50, 200)},
        {"name": "At Risk", "count": random.randint(20, 100), "avg_revenue": random.uniform(1500, 4000)}
    ]
    
    # Calculate totals
    total_customers = sum(segment["count"] for segment in segments)
    total_revenue = sum(segment["count"] * segment["avg_revenue"] for segment in segments)
    
    # Add percentage and format values
    for segment in segments:
        segment["percentage"] = round((segment["count"] / total_customers) * 100, 1)
        segment["avg_revenue"] = round(segment["avg_revenue"], 2)
        segment["total_revenue"] = round(segment["count"] * segment["avg_revenue"], 2)
        segment["revenue_percentage"] = round((segment["total_revenue"] / total_revenue) * 100, 1)
    
    return {
        "segments": segments,
        "total_customers": total_customers,
        "total_revenue": round(total_revenue, 2)
    }

@frappe.whitelist(allow_guest=True)
def get_sentiment_analysis():
    """
    Generate simulated sentiment analysis data from customer interactions
    """
    # Generate random sentiment data
    sentiments = ["Positive", "Neutral", "Negative"]
    weights = [0.6, 0.3, 0.1]  # Biased toward positive for demo
    
    channels = ["Email", "Phone", "Chat", "Social Media", "In Person"]
    
    # Generate last 30 days of data
    today = get_datetime(now_datetime())
    dates = [(add_days(today, -i)).strftime("%Y-%m-%d") for i in range(30, 0, -1)]
    
    daily_data = []
    for date in dates:
        # Random number of interactions per day (50-200)
        interactions = random.randint(50, 200)
        
        # Distribute across sentiments
        sentiment_counts = {
            "Positive": int(interactions * weights[0] * random.uniform(0.9, 1.1)),
            "Neutral": int(interactions * weights[1] * random.uniform(0.9, 1.1)),
            "Negative": int(interactions * weights[2] * random.uniform(0.9, 1.1))
        }
        
        # Adjust to make sure they sum to interactions
        total = sum(sentiment_counts.values())
        if total != interactions:
            diff = interactions - total
            sentiment_counts["Neutral"] += diff
        
        # Distribute across channels
        channel_distribution = {}
        remaining = interactions
        for channel in channels[:-1]:
            channel_count = int(remaining * random.uniform(0.1, 0.3))
            channel_distribution[channel] = channel_count
            remaining -= channel_count
        channel_distribution[channels[-1]] = remaining
        
        daily_data.append({
            "date": date,
            "interactions": interactions,
            "sentiments": sentiment_counts,
            "channels": channel_distribution
        })
    
    # Generate some common phrases
    positive_phrases = [
        {"text": "excellent service", "count": random.randint(30, 100)},
        {"text": "very helpful", "count": random.randint(25, 80)},
        {"text": "great product", "count": random.randint(20, 70)},
        {"text": "highly recommend", "count": random.randint(15, 60)},
        {"text": "thank you", "count": random.randint(40, 120)}
    ]
    
    negative_phrases = [
        {"text": "poor service", "count": random.randint(5, 30)},
        {"text": "not working", "count": random.randint(10, 40)},
        {"text": "disappointed", "count": random.randint(8, 35)},
        {"text": "too expensive", "count": random.randint(7, 25)},
        {"text": "waiting too long", "count": random.randint(6, 20)}
    ]
    
    # Calculate overall sentiment
    total_interactions = sum(day["interactions"] for day in daily_data)
    total_positive = sum(day["sentiments"]["Positive"] for day in daily_data)
    total_neutral = sum(day["sentiments"]["Neutral"] for day in daily_data)
    total_negative = sum(day["sentiments"]["Negative"] for day in daily_data)
    
    sentiment_score = (total_positive - total_negative) / total_interactions * 100
    
    return {
        "daily_data": daily_data,
        "overall_sentiment_score": round(sentiment_score, 1),
        "total_interactions": total_interactions,
        "sentiment_distribution": {
            "Positive": round(total_positive / total_interactions * 100, 1),
            "Neutral": round(total_neutral / total_interactions * 100, 1),
            "Negative": round(total_negative / total_interactions * 100, 1)
        },
        "common_phrases": {
            "positive": positive_phrases,
            "negative": negative_phrases
        }
    }
