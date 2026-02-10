# Clear git merge state
$mergeFiles = @(
    "c:\weeklyleadershipreports\.git\MERGE_HEAD",
    "c:\weeklyleadershipreports\.git\MERGE_MODE", 
    "c:\weeklyleadershipreports\.git\MERGE_MSG",
    "c:\weeklyleadershipreports\.git\.MERGE_MSG.swp",
    "c:\weeklyleadershipreports\.git\AUTO_MERGE"
)

foreach ($file in $mergeFiles) {
    if (Test-Path $file) {
        Remove-Item $file -Force
        Write-Host "Deleted: $file"
    }
}

Write-Host "Merge state cleared successfully"
