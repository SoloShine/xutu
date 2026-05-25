@echo off
setlocal

:: 设置目标输出文件
set "outputFile=merged.txt"

:: 如果输出文件已存在，则删除它（可选）
if exist "%outputFile%" del "%outputFile%"

:: 遍历指定目录下的所有.txt文件
:: 注意：下面的示例使用当前目录（.），你可以替换为具体的路径
for %%f in (*.txt) do (
    :: 将每个文件的内容追加到输出文件中
    type "%%f" >> "%outputFile%"
    :: 可选：在每个文件之间添加一个空行作为分隔符
    echo. >> "%outputFile%"
)

:: 提示用户操作已完成
echo 所有.txt文件的内容已合并到 %outputFile% 中。

:: 暂停以便用户查看结果（可选）
pause

endlocal