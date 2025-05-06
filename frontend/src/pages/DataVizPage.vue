<template>
  <div class="p-6">
    <h1 class="text-2xl font-bold mb-4">Data Visualization Dashboard</h1>
    
    <div v-if="loading" class="flex justify-center items-center h-64">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-700"></div>
    </div>
    
    <div v-else>
      <!-- Sales Forecast Section -->
      <div class="bg-white rounded-lg shadow p-6 mb-6">
        <div class="flex justify-between items-center mb-4">
          <h2 class="text-xl font-semibold">Sales Forecast</h2>
          <button 
            @click="refreshSalesData" 
            class="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          >
            <span class="flex items-center">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh
            </span>
          </button>
        </div>
        
        <!-- Sales Chart -->
        <div class="h-64 mb-6">
          <canvas ref="salesChart"></canvas>
        </div>
        
        <!-- Insights Cards -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div class="bg-blue-50 p-4 rounded-lg border border-blue-200">
            <h3 class="text-sm font-medium text-blue-800 mb-2">Week-over-Week Change</h3>
            <p class="text-2xl font-bold" :class="salesData.insights.week_over_week_change >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ salesData.insights.week_over_week_change >= 0 ? '+' : '' }}{{ salesData.insights.week_over_week_change }}%
            </p>
          </div>
          
          <div class="bg-blue-50 p-4 rounded-lg border border-blue-200">
            <h3 class="text-sm font-medium text-blue-800 mb-2">Projected Monthly Revenue</h3>
            <p class="text-2xl font-bold text-blue-700">
              ${{ formatNumber(salesData.insights.projected_monthly_revenue) }}
            </p>
          </div>
          
          <div class="bg-blue-50 p-4 rounded-lg border border-blue-200">
            <h3 class="text-sm font-medium text-blue-800 mb-2">Forecast Confidence</h3>
            <div class="flex items-center">
              <p class="text-2xl font-bold text-blue-700 mr-2">
                {{ salesData.insights.confidence_score }}%
              </p>
              <div class="w-full bg-gray-200 rounded-full h-2.5">
                <div class="bg-blue-600 h-2.5 rounded-full" :style="`width: ${salesData.insights.confidence_score}%`"></div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- Recommendations -->
        <div class="mb-4">
          <h3 class="text-lg font-medium mb-2">Recommendations</h3>
          <div v-for="(rec, index) in salesData.recommendations" :key="index" 
               class="mb-2 p-3 rounded-lg text-sm" 
               :class="{
                 'bg-green-50 text-green-800 border border-green-200': rec.type === 'success',
                 'bg-yellow-50 text-yellow-800 border border-yellow-200': rec.type === 'warning',
                 'bg-blue-50 text-blue-800 border border-blue-200': rec.type === 'info'
               }">
            {{ rec.message }}
          </div>
        </div>
      </div>
      
      <!-- Customer Segments Section -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div class="bg-white rounded-lg shadow p-6">
          <h2 class="text-xl font-semibold mb-4">Customer Segments</h2>
          
          <!-- Segments Chart -->
          <div class="h-64 mb-4">
            <canvas ref="segmentsChart"></canvas>
          </div>
          
          <div class="text-sm text-gray-600">
            <p>Total Customers: <span class="font-semibold">{{ formatNumber(customerData.total_customers) }}</span></p>
            <p>Total Revenue: <span class="font-semibold">${{ formatNumber(customerData.total_revenue) }}</span></p>
          </div>
        </div>
        
        <!-- Sentiment Analysis Section -->
        <div class="bg-white rounded-lg shadow p-6">
          <h2 class="text-xl font-semibold mb-4">Customer Sentiment</h2>
          
          <!-- Sentiment Chart -->
          <div class="h-64 mb-4">
            <canvas ref="sentimentChart"></canvas>
          </div>
          
          <div class="text-sm">
            <p class="text-gray-600">
              Overall Sentiment Score: 
              <span class="font-semibold" :class="{
                'text-green-600': sentimentData.overall_sentiment_score > 50,
                'text-yellow-600': sentimentData.overall_sentiment_score >= 30 && sentimentData.overall_sentiment_score <= 50,
                'text-red-600': sentimentData.overall_sentiment_score < 30
              }">
                {{ sentimentData.overall_sentiment_score }}
              </span>
            </p>
            <p class="text-gray-600">Total Interactions: <span class="font-semibold">{{ formatNumber(sentimentData.total_interactions) }}</span></p>
          </div>
        </div>
      </div>
      
      <!-- Common Phrases -->
      <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-semibold mb-4">Common Customer Phrases</h2>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h3 class="text-lg font-medium text-green-700 mb-2">Positive Phrases</h3>
            <div class="space-y-2">
              <div v-for="(phrase, index) in sentimentData.common_phrases.positive" :key="'pos-'+index"
                   class="flex justify-between p-2 bg-green-50 rounded border border-green-200">
                <span class="font-medium">"{{ phrase.text }}"</span>
                <span class="text-green-700">{{ phrase.count }} mentions</span>
              </div>
            </div>
          </div>
          
          <div>
            <h3 class="text-lg font-medium text-red-700 mb-2">Negative Phrases</h3>
            <div class="space-y-2">
              <div v-for="(phrase, index) in sentimentData.common_phrases.negative" :key="'neg-'+index"
                   class="flex justify-between p-2 bg-red-50 rounded border border-red-200">
                <span class="font-medium">"{{ phrase.text }}"</span>
                <span class="text-red-700">{{ phrase.count }} mentions</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { createResource } from 'frappe-ui'
import Chart from 'chart.js/auto'

// Data refs
const loading = ref(true)
const salesData = ref({
  historical_data: [],
  forecast_data: [],
  insights: {
    week_over_week_change: 0,
    projected_monthly_revenue: 0,
    confidence_score: 0
  },
  recommendations: []
})
const customerData = ref({
  segments: [],
  total_customers: 0,
  total_revenue: 0
})
const sentimentData = ref({
  daily_data: [],
  overall_sentiment_score: 0,
  total_interactions: 0,
  sentiment_distribution: {
    Positive: 0,
    Neutral: 0,
    Negative: 0
  },
  common_phrases: {
    positive: [],
    negative: []
  }
})

// Chart refs
const salesChart = ref(null)
const segmentsChart = ref(null)
const sentimentChart = ref(null)

// Chart instances
let salesChartInstance = null
let segmentsChartInstance = null
let sentimentChartInstance = null

// API Resources
const salesResource = createResource({
  url: 'crm.api.dataviz.get_sales_forecast',
  onSuccess: (data) => {
    salesData.value = data
    renderSalesChart()
  },
  onError: (error) => {
    console.error('Error fetching sales data:', error)
  }
})

const customerResource = createResource({
  url: 'crm.api.dataviz.get_customer_segments',
  onSuccess: (data) => {
    customerData.value = data
    renderSegmentsChart()
  },
  onError: (error) => {
    console.error('Error fetching customer data:', error)
  }
})

const sentimentResource = createResource({
  url: 'crm.api.dataviz.get_sentiment_analysis',
  onSuccess: (data) => {
    sentimentData.value = data
    renderSentimentChart()
    loading.value = false
  },
  onError: (error) => {
    console.error('Error fetching sentiment data:', error)
    loading.value = false
  }
})

// Methods
function refreshSalesData() {
  salesResource.submit()
}

function formatNumber(num) {
  return new Intl.NumberFormat().format(num)
}

function renderSalesChart() {
  if (salesChartInstance) {
    salesChartInstance.destroy()
  }
  
  const ctx = salesChart.value.getContext('2d')
  
  // Prepare data
  const labels = [
    ...salesData.value.historical_data.map(d => d.date),
    ...salesData.value.forecast_data.map(d => d.date)
  ]
  
  const historicalSales = salesData.value.historical_data.map(d => d.sales)
  const forecastSales = salesData.value.forecast_data.map(d => d.sales)
  
  // Fill with nulls for alignment
  const historicalDataset = [
    ...historicalSales,
    ...Array(salesData.value.forecast_data.length).fill(null)
  ]
  
  const forecastDataset = [
    ...Array(salesData.value.historical_data.length).fill(null),
    ...forecastSales
  ]
  
  // Upper and lower bounds for forecast
  const upperBounds = [
    ...Array(salesData.value.historical_data.length).fill(null),
    ...salesData.value.forecast_data.map(d => d.upper_bound)
  ]
  
  const lowerBounds = [
    ...Array(salesData.value.historical_data.length).fill(null),
    ...salesData.value.forecast_data.map(d => d.lower_bound)
  ]
  
  salesChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Historical Sales',
          data: historicalDataset,
          borderColor: 'rgb(59, 130, 246)',
          backgroundColor: 'rgba(59, 130, 246, 0.5)',
          borderWidth: 2,
          tension: 0.1
        },
        {
          label: 'Forecast',
          data: forecastDataset,
          borderColor: 'rgb(139, 92, 246)',
          backgroundColor: 'rgba(139, 92, 246, 0.5)',
          borderWidth: 2,
          borderDash: [5, 5],
          tension: 0.1
        },
        {
          label: 'Upper Bound',
          data: upperBounds,
          borderColor: 'rgba(139, 92, 246, 0.3)',
          backgroundColor: 'rgba(139, 92, 246, 0)',
          borderWidth: 1,
          borderDash: [3, 3],
          pointRadius: 0,
          tension: 0.1,
          fill: '+2'
        },
        {
          label: 'Lower Bound',
          data: lowerBounds,
          borderColor: 'rgba(139, 92, 246, 0.3)',
          backgroundColor: 'rgba(139, 92, 246, 0.1)',
          borderWidth: 1,
          borderDash: [3, 3],
          pointRadius: 0,
          tension: 0.1,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        intersect: false,
        mode: 'index'
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: function(context) {
              let label = context.dataset.label || '';
              if (label) {
                label += ': ';
              }
              if (context.parsed.y !== null) {
                label += new Intl.NumberFormat('en-US', {
                  style: 'currency',
                  currency: 'USD'
                }).format(context.parsed.y);
              }
              return label;
            }
          }
        },
        legend: {
          position: 'top',
          labels: {
            filter: function(item, chart) {
              // Hide upper/lower bound from legend
              return !item.text.includes('Bound');
            }
          }
        }
      },
      scales: {
        x: {
          grid: {
            display: false
          },
          ticks: {
            maxRotation: 45,
            minRotation: 45
          }
        },
        y: {
          beginAtZero: false,
          grid: {
            drawBorder: false
          },
          ticks: {
            callback: function(value) {
              return '$' + value.toLocaleString();
            }
          }
        }
      }
    }
  })
}

function renderSegmentsChart() {
  if (segmentsChartInstance) {
    segmentsChartInstance.destroy()
  }
  
  const ctx = segmentsChart.value.getContext('2d')
  
  segmentsChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: customerData.value.segments.map(s => s.name),
      datasets: [
        {
          data: customerData.value.segments.map(s => s.count),
          backgroundColor: [
            'rgba(54, 162, 235, 0.7)',
            'rgba(75, 192, 192, 0.7)',
            'rgba(255, 206, 86, 0.7)',
            'rgba(153, 102, 255, 0.7)',
            'rgba(255, 99, 132, 0.7)'
          ],
          borderColor: [
            'rgba(54, 162, 235, 1)',
            'rgba(75, 192, 192, 1)',
            'rgba(255, 206, 86, 1)',
            'rgba(153, 102, 255, 1)',
            'rgba(255, 99, 132, 1)'
          ],
          borderWidth: 1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        tooltip: {
          callbacks: {
            label: function(context) {
              const segment = customerData.value.segments[context.dataIndex];
              const percentage = segment.percentage;
              const avgRevenue = segment.avg_revenue;
              
              return [
                `${segment.name}: ${segment.count} customers (${percentage}%)`,
                `Avg Revenue: $${avgRevenue.toLocaleString()}`
              ];
            }
          }
        },
        legend: {
          position: 'right'
        }
      }
    }
  })
}

function renderSentimentChart() {
  if (sentimentChartInstance) {
    sentimentChartInstance.destroy()
  }
  
  const ctx = sentimentChart.value.getContext('2d')
  
  sentimentChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Positive', 'Neutral', 'Negative'],
      datasets: [
        {
          data: [
            sentimentData.value.sentiment_distribution.Positive,
            sentimentData.value.sentiment_distribution.Neutral,
            sentimentData.value.sentiment_distribution.Negative
          ],
          backgroundColor: [
            'rgba(75, 192, 192, 0.7)',
            'rgba(255, 206, 86, 0.7)',
            'rgba(255, 99, 132, 0.7)'
          ],
          borderColor: [
            'rgba(75, 192, 192, 1)',
            'rgba(255, 206, 86, 1)',
            'rgba(255, 99, 132, 1)'
          ],
          borderWidth: 1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              return `${context.parsed.x}% of interactions`;
            }
          }
        }
      },
      scales: {
        x: {
          beginAtZero: true,
          max: 100,
          ticks: {
            callback: function(value) {
              return value + '%';
            }
          }
        }
      }
    }
  })
}

// Lifecycle hooks
onMounted(() => {
  // Fetch all data
  salesResource.submit()
  customerResource.submit()
  sentimentResource.submit()
})
</script>
