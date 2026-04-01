echo "Current Branch:"
git branch
echo "Enter commit message... (type 'void' to skip)"
git add .
read message
if [[ "${message,,}" != "void" ]]; then
	git commit -m "${message}"
	git push
	echo "commit and push success."
else 
	echo "commit and push was skipped."
fi

echo "Press Enter to close..."
read
