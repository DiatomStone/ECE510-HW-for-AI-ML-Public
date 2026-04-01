echo "Current Branch:"
git branch
echo "Enter commit message..."
git add .
read message
git commit -m "${message}"
git push
