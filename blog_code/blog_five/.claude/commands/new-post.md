---
allowed-tools: Write, Read, Glob
argument-hint: [title] [date] 
description: Create a new blog post draft
---

Create a new blog post using the configuration in @config.yaml

## Instructions

1. Read the blog configuration from config.yaml to get:
    - Blog path
    - Posts folder structure
    - Front matter template
    - Date format and slug pattern

2. Generate the post metadata:
    - Parse `$ARGUMENTS` to extract title and optional date
    - Date: Use specified date if provided, otherwise today's date formatted per `date_format` (default: 9AM UTC)
    - Slug: Based on `slug_pattern` + title (e.g., "02-09-my-post-title")
    - Title: Use provided title, or "New Post" if none given
    - Year: From the date (for folder path)

3. Create the file:
    - Path: `{blog.path}/{blog.posts_folder}/{year}/{slug}.md`
    - Content: Front matter template with placeholders substituted
    - Use the Write tool (NOT Bash) to create the file

4. Confirm creation:
    - Report the full path of the created file
    - Show the front matter that was generated
    - Remind user the post is created as a draft

## Arguments

- `$ARGUMENTS`: Optional command from user - probably specifying date and / or title for post. If not provided use today's date and "New Post" 

## Example

`/new-post My Awesome Blog Post` creates:
  - File: `content/posts/2026/02-09-my-awesome-blog-post.md`

`/new-post My Awesome Blog Post 2026-03-15` creates:
- File: `content/posts/2026/03-15-my-awesome-blog-post.md`
