#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Running database migrations"
# Use psql to execute our schema SQL
PGPASSWORD=$DATABASE_PASSWORD psql -h $DATABASE_HOST -U $DATABASE_USER -d $DATABASE_NAME -f schema.sql

echo "Database migration completed"

# Run pip install
pip install -r requirements.txt 