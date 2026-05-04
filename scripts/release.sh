#!/bin/bash

# 发布脚本
VERSION=$1

if [ -z "$VERSION" ]; then
    echo "请提供版本号，例如: ./scripts/release.sh 1.1.0"
    exit 1
fi

echo "准备发布版本 v$VERSION"

# 确保在main分支
git checkout main
git pull origin main

# 更新版本号
sed -i "s/version='.*'/version='$VERSION'/" setup.py
sed -i "s/## \[未发布\]/## \[未发布\]\n\n## [$VERSION] - $(date +%Y-%m-%d)/" CHANGELOG.md

# 提交更改
git add .
git commit -m "chore(release): 发布版本 $VERSION"
git tag -a "v$VERSION" -m "版本 $VERSION"

# 推送
git push origin main --tags

echo "✅ 版本 v$VERSION 已发布"