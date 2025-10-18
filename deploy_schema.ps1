# PowerShell script to deploy the CSV-matched engagement schema
Write-Host "Deploying CSV-matched engagement schema to Supabase..." -ForegroundColor Green

# Read the SQL schema file
$schemaPath = "c:\Users\troy.noeldner\OneDrive - North Dakota University System\Documents\und-reporting-tool\SIMPLIFIED_ENGAGEMENT_SCHEMA.sql"

if (Test-Path $schemaPath) {
    $schemaContent = Get-Content $schemaPath -Raw
    Write-Host "Schema file loaded successfully" -ForegroundColor Green
    Write-Host "Schema size: $($schemaContent.Length) characters" -ForegroundColor Cyan
    
    # Display first few lines of schema for verification
    Write-Host "`nFirst 200 characters of schema:" -ForegroundColor Yellow
    Write-Host $schemaContent.Substring(0, [Math]::Min(200, $schemaContent.Length)) -ForegroundColor Gray
    
    Write-Host "`n✅ Schema ready for deployment" -ForegroundColor Green
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Copy the schema content from SIMPLIFIED_ENGAGEMENT_SCHEMA.sql" -ForegroundColor White
    Write-Host "2. Run it in Supabase SQL Editor" -ForegroundColor White
    Write-Host "3. Test the engagement sync in the Streamlit app" -ForegroundColor White
} else {
    Write-Host "❌ Schema file not found at: $schemaPath" -ForegroundColor Red
}