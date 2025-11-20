-- Supabase schema for the recommendation engine
-- Run this in your Supabase SQL editor to set up the database

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    price DECIMAL(10,2),
    embedding vector(384),  -- For vector similarity search
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS idx_products_embedding
ON products USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create index for product_id lookups
CREATE INDEX IF NOT EXISTS idx_products_product_id ON products(product_id);

-- Create index for category filtering
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);

-- Create full-text search index
CREATE INDEX IF NOT EXISTS idx_products_search
ON products USING GIN (to_tsvector('english', name || ' ' || COALESCE(description, '')));

-- Product events table for event streaming
CREATE TABLE IF NOT EXISTS product_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type TEXT NOT NULL CHECK (event_type IN ('create', 'update', 'delete')),
    product_id TEXT NOT NULL,
    data JSONB NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for efficient event processing
CREATE INDEX IF NOT EXISTS idx_product_events_processed ON product_events(processed, created_at);
CREATE INDEX IF NOT EXISTS idx_product_events_product_id ON product_events(product_id);

-- User behavior tracking
CREATE TABLE IF NOT EXISTS user_views (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

-- Index for user behavior queries
CREATE INDEX IF NOT EXISTS idx_user_views_user_time ON user_views(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_user_views_product ON user_views(product_id);

-- Category popularity tracking
CREATE TABLE IF NOT EXISTS category_popularity (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category TEXT UNIQUE NOT NULL,
    view_count INTEGER DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Function to automatically update updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to auto-update updated_at on products
CREATE TRIGGER update_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to increment category popularity
CREATE OR REPLACE FUNCTION increment_category_popularity()
RETURNS TRIGGER AS $$
BEGIN
    -- Get the category of the viewed product
    INSERT INTO category_popularity (category, view_count, last_updated)
    SELECT p.category, 1, NOW()
    FROM products p
    WHERE p.product_id = NEW.product_id
    ON CONFLICT (category)
    DO UPDATE SET
        view_count = category_popularity.view_count + 1,
        last_updated = NOW();

    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to auto-update category popularity on user views
CREATE TRIGGER update_category_popularity
    AFTER INSERT ON user_views
    FOR EACH ROW
    EXECUTE FUNCTION increment_category_popularity();

-- Insert some sample data for testing
INSERT INTO products (product_id, name, description, category, price) VALUES
('test-product-1', 'AI-Powered Headphones', 'Wireless headphones with AI noise cancellation', 'electronics', 299.99),
('test-product-2', 'Smart Fitness Tracker', 'Advanced fitness tracking with health monitoring', 'electronics', 199.99),
('test-product-3', 'Programming Book: Python ML', 'Complete guide to machine learning with Python', 'books', 49.99),
('test-product-4', 'Ergonomic Desk Chair', 'Professional office chair with lumbar support', 'furniture', 399.99)
ON CONFLICT (product_id) DO NOTHING;

-- Create Row Level Security (RLS) policies if needed
-- ALTER TABLE products ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE product_events ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE user_views ENABLE ROW LEVEL SECURITY;

-- Example RLS policy (adjust based on your authentication needs)
-- CREATE POLICY "Public products are viewable by everyone" ON products FOR SELECT USING (true);
-- CREATE POLICY "Users can insert their own views" ON user_views FOR INSERT WITH CHECK (true);

-- Grant necessary permissions (adjust based on your needs)
-- GRANT ALL ON products TO authenticated;
-- GRANT ALL ON product_events TO authenticated;
-- GRANT ALL ON user_views TO authenticated;
-- GRANT ALL ON category_popularity TO authenticated;