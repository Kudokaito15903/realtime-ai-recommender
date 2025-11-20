#!/usr/bin/env python3
"""
Performance Comparison: Current vs Enhanced System
Simulates and compares performance metrics between TF-IDF and Hybrid Search systems
"""

import time
import random
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import queue

# Simulation parameters
np.random.seed(42)
random.seed(42)

@dataclass
class SearchResult:
    query: str
    results_count: int
    relevance_score: float
    response_time_ms: float
    memory_usage_mb: float
    cpu_usage_percent: float

@dataclass
class SystemMetrics:
    concurrent_users: int
    avg_response_time: float
    p95_response_time: float
    p99_response_time: float
    throughput_rps: float
    memory_usage_gb: float
    cpu_usage_percent: float
    error_rate_percent: float

class CurrentSystemSimulator:
    """Simulates the current TF-IDF + Redis system"""

    def __init__(self):
        self.name = "Current System (TF-IDF + Redis)"
        self.base_latency = 80  # ms
        self.vector_dim = 384
        self.memory_usage = 4.0  # GB
        self.max_concurrent = 500

    def search(self, query: str, concurrent_load: int = 1) -> SearchResult:
        """Simulate a search operation"""

        # Base performance
        base_time = self.base_latency

        # Add load-based latency
        load_factor = min(concurrent_load / self.max_concurrent, 2.0)
        load_latency = base_time * load_factor * 0.5

        # Add random variance
        variance = np.random.normal(0, base_time * 0.2)

        total_time = base_time + load_latency + variance
        total_time = max(total_time, 10)  # Minimum 10ms

        # Simulate relevance (TF-IDF is good but not great)
        relevance = np.random.normal(0.65, 0.15)
        relevance = np.clip(relevance, 0.1, 1.0)

        # Memory and CPU usage
        memory_mb = 50 + (concurrent_load * 2)
        cpu_percent = 20 + (concurrent_load * 0.5)

        return SearchResult(
            query=query,
            results_count=random.randint(5, 25),
            relevance_score=relevance,
            response_time_ms=total_time,
            memory_usage_mb=memory_mb,
            cpu_usage_percent=min(cpu_percent, 90)
        )

class EnhancedSystemSimulator:
    """Simulates the enhanced CLIP + BM25 + Pinecone system"""

    def __init__(self):
        self.name = "Enhanced System (CLIP + BM25 + Pinecone)"
        self.base_latency = 200  # ms (CLIP inference + Pinecone)
        self.vector_dim = 512
        self.memory_usage = 12.0  # GB
        self.max_concurrent = 200  # Limited by CLIP model
        self.clip_inference_time = 150  # ms
        self.pinecone_latency = 50  # ms

    def search(self, query: str, concurrent_load: int = 1, search_type: str = "text") -> SearchResult:
        """Simulate a search operation"""

        # Base CLIP inference time
        if search_type == "image":
            clip_time = self.clip_inference_time * 1.5  # Images take longer
        else:
            clip_time = self.clip_inference_time

        # Pinecone API latency
        pinecone_time = self.pinecone_latency

        # Load-based performance degradation
        if concurrent_load > self.max_concurrent:
            # System becomes overloaded
            overload_factor = concurrent_load / self.max_concurrent
            clip_time *= overload_factor
            pinecone_time *= (1 + (overload_factor - 1) * 0.3)

        # Queue waiting time for CLIP model
        queue_time = max(0, (concurrent_load - 50) * 2)

        # Total time
        total_time = clip_time + pinecone_time + queue_time

        # Add random variance
        variance = np.random.normal(0, total_time * 0.15)
        total_time += variance
        total_time = max(total_time, 50)  # Minimum 50ms

        # Enhanced relevance (much better with hybrid search)
        base_relevance = 0.85 if search_type == "text" else 0.90
        relevance = np.random.normal(base_relevance, 0.1)
        relevance = np.clip(relevance, 0.3, 1.0)

        # Memory and CPU usage (higher due to CLIP model)
        memory_mb = 200 + (concurrent_load * 5)
        cpu_percent = 40 + (concurrent_load * 1.2)

        return SearchResult(
            query=query,
            results_count=random.randint(15, 40),
            relevance_score=relevance,
            response_time_ms=total_time,
            memory_usage_mb=memory_mb,
            cpu_usage_percent=min(cpu_percent, 95)
        )

class LoadTestSimulator:
    """Simulates load testing scenarios"""

    def __init__(self):
        self.current_system = CurrentSystemSimulator()
        self.enhanced_system = EnhancedSystemSimulator()

    def simulate_concurrent_load(self, system, concurrent_users: int, duration_seconds: int = 60) -> SystemMetrics:
        """Simulate concurrent load on a system"""

        print(f"Testing {system.name} with {concurrent_users} concurrent users...")

        results = []
        errors = 0
        start_time = time.time()

        def worker():
            local_results = []
            while time.time() - start_time < duration_seconds:
                try:
                    query = f"search_query_{random.randint(1, 1000)}"
                    result = system.search(query, concurrent_users)
                    local_results.append(result)
                    time.sleep(random.uniform(0.1, 2.0))  # User think time
                except Exception:
                    nonlocal errors
                    errors += 1

            return local_results

        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=min(concurrent_users, 50)) as executor:
            futures = [executor.submit(worker) for _ in range(min(concurrent_users, 50))]

            for future in as_completed(futures):
                results.extend(future.result())

        # Calculate metrics
        if not results:
            return SystemMetrics(concurrent_users, 0, 0, 0, 0, 0, 0, 100)

        response_times = [r.response_time_ms for r in results]

        return SystemMetrics(
            concurrent_users=concurrent_users,
            avg_response_time=np.mean(response_times),
            p95_response_time=np.percentile(response_times, 95),
            p99_response_time=np.percentile(response_times, 99),
            throughput_rps=len(results) / duration_seconds,
            memory_usage_gb=system.memory_usage,
            cpu_usage_percent=np.mean([r.cpu_usage_percent for r in results]),
            error_rate_percent=(errors / (len(results) + errors)) * 100
        )

    def run_comprehensive_benchmark(self) -> pd.DataFrame:
        """Run a comprehensive benchmark comparing both systems"""

        print("🚀 Starting Comprehensive Performance Benchmark...")
        print("=" * 60)

        test_loads = [10, 25, 50, 100, 200, 300, 500]
        results = []

        for load in test_loads:
            print(f"\nTesting with {load} concurrent users...")

            # Test current system
            current_metrics = self.simulate_concurrent_load(self.current_system, load, 30)
            results.append({
                'system': 'Current (TF-IDF)',
                'concurrent_users': load,
                'avg_response_time': current_metrics.avg_response_time,
                'p95_response_time': current_metrics.p95_response_time,
                'throughput_rps': current_metrics.throughput_rps,
                'memory_gb': current_metrics.memory_usage_gb,
                'cpu_percent': current_metrics.cpu_usage_percent,
                'error_rate': current_metrics.error_rate_percent
            })

            # Test enhanced system (skip high loads that would overload it)
            if load <= 300:
                enhanced_metrics = self.simulate_concurrent_load(self.enhanced_system, load, 30)
                results.append({
                    'system': 'Enhanced (CLIP+BM25)',
                    'concurrent_users': load,
                    'avg_response_time': enhanced_metrics.avg_response_time,
                    'p95_response_time': enhanced_metrics.p95_response_time,
                    'throughput_rps': enhanced_metrics.throughput_rps,
                    'memory_gb': enhanced_metrics.memory_usage_gb,
                    'cpu_percent': enhanced_metrics.cpu_usage_percent,
                    'error_rate': enhanced_metrics.error_rate_percent
                })

        return pd.DataFrame(results)

def create_performance_visualizations(df: pd.DataFrame):
    """Create performance comparison visualizations"""

    plt.style.use('seaborn-v0_8')
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('Performance Comparison: Current vs Enhanced System', fontsize=16, fontweight='bold')

    # Response Time Comparison
    ax = axes[0, 0]
    for system in df['system'].unique():
        data = df[df['system'] == system]
        ax.plot(data['concurrent_users'], data['avg_response_time'],
               marker='o', linewidth=2, label=system)
    ax.set_xlabel('Concurrent Users')
    ax.set_ylabel('Avg Response Time (ms)')
    ax.set_title('Response Time vs Load')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Throughput Comparison
    ax = axes[0, 1]
    for system in df['system'].unique():
        data = df[df['system'] == system]
        ax.plot(data['concurrent_users'], data['throughput_rps'],
               marker='s', linewidth=2, label=system)
    ax.set_xlabel('Concurrent Users')
    ax.set_ylabel('Throughput (req/sec)')
    ax.set_title('Throughput vs Load')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Memory Usage
    ax = axes[0, 2]
    for system in df['system'].unique():
        data = df[df['system'] == system]
        ax.plot(data['concurrent_users'], data['memory_gb'],
               marker='^', linewidth=2, label=system)
    ax.set_xlabel('Concurrent Users')
    ax.set_ylabel('Memory Usage (GB)')
    ax.set_title('Memory Usage vs Load')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # P95 Response Time
    ax = axes[1, 0]
    for system in df['system'].unique():
        data = df[df['system'] == system]
        ax.plot(data['concurrent_users'], data['p95_response_time'],
               marker='D', linewidth=2, label=system)
    ax.set_xlabel('Concurrent Users')
    ax.set_ylabel('P95 Response Time (ms)')
    ax.set_title('P95 Latency vs Load')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # CPU Usage
    ax = axes[1, 1]
    for system in df['system'].unique():
        data = df[df['system'] == system]
        ax.plot(data['concurrent_users'], data['cpu_percent'],
               marker='v', linewidth=2, label=system)
    ax.set_xlabel('Concurrent Users')
    ax.set_ylabel('CPU Usage (%)')
    ax.set_title('CPU Usage vs Load')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Error Rate
    ax = axes[1, 2]
    for system in df['system'].unique():
        data = df[df['system'] == system]
        ax.plot(data['concurrent_users'], data['error_rate'],
               marker='x', linewidth=2, label=system)
    ax.set_xlabel('Concurrent Users')
    ax.set_ylabel('Error Rate (%)')
    ax.set_title('Error Rate vs Load')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('performance_comparison.png', dpi=300, bbox_inches='tight')
    plt.show()

def analyze_search_quality():
    """Analyze search quality differences between systems"""

    print("\n🎯 Search Quality Analysis")
    print("=" * 40)

    current_sim = CurrentSystemSimulator()
    enhanced_sim = EnhancedSystemSimulator()

    # Test different query types
    query_types = [
        ("exact_match", "Nike Air Jordan"),
        ("semantic", "formal business attire"),
        ("descriptive", "red summer dress casual"),
        ("brand", "Adidas running shoes"),
        ("style", "vintage denim jacket")
    ]

    quality_results = []

    for query_type, query in query_types:
        # Current system
        current_result = current_sim.search(query)

        # Enhanced system
        enhanced_text = enhanced_sim.search(query, search_type="text")

        quality_results.append({
            'query_type': query_type,
            'query': query,
            'current_relevance': current_result.relevance_score,
            'enhanced_relevance': enhanced_text.relevance_score,
            'improvement': enhanced_text.relevance_score - current_result.relevance_score,
            'current_results': current_result.results_count,
            'enhanced_results': enhanced_text.results_count
        })

    quality_df = pd.DataFrame(quality_results)

    print(quality_df[['query_type', 'current_relevance', 'enhanced_relevance', 'improvement']].round(3))

    print(f"\nAverage Relevance Improvement: {quality_df['improvement'].mean():.3f}")
    print(f"Best Improvement: {quality_df['improvement'].max():.3f} ({quality_df.loc[quality_df['improvement'].idxmax(), 'query_type']})")

    return quality_df

def cost_analysis():
    """Analyze cost implications of the upgrade"""

    print("\n💰 Cost Analysis")
    print("=" * 30)

    current_costs = {
        "Redis Hosting": 50,
        "Compute (API)": 100,
        "Total Monthly": 150
    }

    enhanced_costs = {
        "Pinecone (Starter)": 200,
        "GPU Compute (CLIP)": 300,
        "Redis Hosting": 50,
        "API Compute": 150,
        "Monitoring & Ops": 100,
        "Total Monthly": 800
    }

    print("Current System Costs (Monthly):")
    for item, cost in current_costs.items():
        print(f"  {item}: ${cost}")

    print("\nEnhanced System Costs (Monthly):")
    for item, cost in enhanced_costs.items():
        print(f"  {item}: ${cost}")

    print(f"\nCost Increase: ${enhanced_costs['Total Monthly'] - current_costs['Total Monthly']} (+{((enhanced_costs['Total Monthly'] / current_costs['Total Monthly']) - 1) * 100:.0f}%)")

    return current_costs, enhanced_costs

def main():
    """Run the complete performance analysis"""

    print("🔬 Performance Comparison Analysis")
    print("Current System vs Enhanced Hybrid Search System")
    print("=" * 60)

    # Initialize simulator
    simulator = LoadTestSimulator()

    # Run comprehensive benchmark
    df = simulator.run_comprehensive_benchmark()

    # Display results
    print("\n📊 Benchmark Results Summary:")
    print(df.pivot_table(
        index='concurrent_users',
        columns='system',
        values=['avg_response_time', 'throughput_rps', 'memory_gb']
    ).round(2))

    # Create visualizations
    create_performance_visualizations(df)

    # Search quality analysis
    quality_df = analyze_search_quality()

    # Cost analysis
    cost_analysis()

    # Summary recommendations
    print("\n🎯 SUMMARY & RECOMMENDATIONS")
    print("=" * 50)

    # Find optimal load for each system
    current_data = df[df['system'] == 'Current (TF-IDF)']
    enhanced_data = df[df['system'] == 'Enhanced (CLIP+BM25)']

    # Find where response time crosses 500ms threshold
    current_optimal = current_data[current_data['avg_response_time'] < 500]['concurrent_users'].max()
    enhanced_optimal = enhanced_data[enhanced_data['avg_response_time'] < 500]['concurrent_users'].max()

    print(f"Optimal Load (< 500ms response):")
    print(f"  Current System: {current_optimal} users")
    print(f"  Enhanced System: {enhanced_optimal} users")

    print(f"\nSearch Quality Improvement: +{quality_df['improvement'].mean():.0%}")
    print(f"Infrastructure Cost Increase: +433%")

    print(f"\n✅ RECOMMEND ENHANCED SYSTEM IF:")
    print(f"  - Search quality is critical for business")
    print(f"  - Budget allows 5x cost increase")
    print(f"  - User base < {enhanced_optimal} concurrent users")
    print(f"  - Team has ML/AI expertise")

    print(f"\n⚠️  STICK WITH CURRENT SYSTEM IF:")
    print(f"  - Current search quality is sufficient")
    print(f"  - Cost is a major constraint")
    print(f"  - High concurrency is required (>{enhanced_optimal} users)")
    print(f"  - Simple product catalog")

if __name__ == "__main__":
    main()