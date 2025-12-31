-- Create the content table
CREATE TABLE IF NOT EXISTS public.content (
    content_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT,
    category TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    status TEXT DEFAULT 'published',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable Row Level Security (RLS) - Optional but recommended
ALTER TABLE public.content ENABLE ROW LEVEL SECURITY;

-- Create policies (Adjust as needed for your application's security model)
-- Allow read access to everyone
CREATE POLICY "Enable read access for all users" ON public.content
    FOR SELECT USING (true);

-- Allow insert/update/delete access only to service role (backend) or authenticated users
-- For now, allowing all for simplicity if accessing via service role key which bypasses RLS
-- But strictly speaking, service role key bypasses RLS so specific policies for it aren't needed.
-- Policies below are for authenticated users if you use them.

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_content_category ON public.content(category);
CREATE INDEX IF NOT EXISTS idx_content_status ON public.content(status);
CREATE INDEX IF NOT EXISTS idx_content_tags ON public.content USING GIN (tags);
