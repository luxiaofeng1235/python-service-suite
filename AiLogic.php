<?php

namespace app\api\logic;

use app\admin\logic\AdvertisementLogic;
use app\common\basics\Logic;
use app\common\logic\AccountLogLogic;
use app\common\model\AccountLog;
use app\common\model\ai\AiChatLog;
use app\common\model\ai\AiDecodeHongbaoLog;
use app\common\model\ai\AiHongbao;
use app\common\model\ai\AiHongbaoLog;
use app\common\model\ai\AiHongbaoRank;
use app\common\model\ai\AiSpeedHongbao;
use app\common\model\ai\AiSpeedHongbaoLog;
use app\common\model\ai\AiToWork;
use app\common\model\ai_theater\AiTheaterModel;
use app\common\model\games\GamesUserBag;
use app\common\model\jiujie\UserMetaPointLog;
use app\common\model\jiujie\UserProfile;
use app\common\model\user\User;
use app\common\server\AesServer;
use app\common\server\ConfigServer;
use app\common\server\FileServer;
use app\common\server\JsonServer;
use app\common\server\storage\Driver;
use app\common\server\storage\engine\Aliyun;
use app\common\server\UrlServer;
use app\services\ElasticsearchService;
use Carbon\Carbon;
use Exception;
use GuzzleHttp\Client;
use GuzzleHttp\Psr7\Utils;
use GuzzleHttp\Exception\GuzzleException;
use GuzzleHttp\Psr7\Request;
use OSS\Credentials\EnvironmentVariableCredentialsProvider;
use OSS\OssClient;
use stdClass;
use think\facade\App;
use think\facade\Filesystem;
use Think\Storage\Driver\File;

class AiLogic extends Logic
{
    private const QW_KEY = 'sk-OTVwdAIbvI';
    private const QW_OPEN_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions';
    private const QW_DS_URL = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation';
    private const QW_IMAGE_URL = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis';
    private const QW_VIDEO_URL = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis';
    private const QW_VIDEO_URL_FACE_DETECT = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/image2video/face-detect';
    private const QW_VIDEO_URL_FACE_SYNTHESIS = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/image2video/video-synthesis/';

    const QWEN_VL_MAX = 'qwen-vl-max';

    private $url = '';
    private $model = '';
    private $system = '';
    private $search = false;
    private $chat = '';
    private $reasoning_content = '';

    public function getChatLogList($params, $uid)
    {
        $page = $params['page'];
        $pageSize = 10;
        $model = AiChatLog::where('model_id', $params['model'])
            ->where('user_id', $uid)
            ->order('id', 'desc');
        //计算总页数
        $total = $model->count();
        $show = ($total === 0) ? 0 : ceil($total / $pageSize);
        $model = $model->page($page, $pageSize)->select();
        $list = [];
        foreach ($model as $item) {
            $content = json_decode($item->chat, true);
            if (is_array($content)) {
                // 获取第一句话，同时要判断数组第一个元素是否存在
                if (!isset($content[0])) {
                    continue;
                }
                $content = $content[0];
                $content = $content['content'];
            } else {
                $content = '';
            }
            $list[] = [
                'chat_id' => $item->id,
                'content' => json_decode($item->chat, true)[0]['content'],
                'create_time' => $item->create_time
            ];
        }
        return JsonServer::success('获取成功', [
            'page' => $page,
            'page_count' => $show,
            'total' => $total,
            'list' => $list
        ]);
    }

    public function getChatLogs($params, $uid)
    {
        $id = $params['chat_id'];
        $chat = AiChatLog::where('id', $id)->where('user_id', $uid)->find();
        if (!$chat) {
            return JsonServer::error('聊天记录不存在');
        }
        $chat = json_decode($chat->chat, true);
        return JsonServer::success('获取成功', $chat);
    }

    public function delChatLog($params, $uid)
    {
        $id = $params['chat_id'];
        $chat = AiChatLog::where('user_id', $uid)->find($id);
        if (!$chat) {
            return JsonServer::error('聊天记录不存在');
        }
        $chat->delete();
        return JsonServer::success('删除成功');
    }

    public function sendStream2($parmas, $uid)
    {
        // 允许脚本在客户端断开连接后继续执行
        ignore_user_abort(true);

        $model = $parmas['model'];
        $chat_id = $parmas['chat_id'];
        $msg = $parmas['msg'];
        $restart = $parmas['restart'];
        $is_deep_reflection = $parmas['is_deep_reflection'] ?? 0; // 是发深度思索，默认否
        $chat = $this->getChatLog($chat_id, $uid, $model);
        if ($chat === false) {
            return JsonServer::error('聊天记录不存在');
        }

        $this->initializeModel($model, $is_deep_reflection);

        $messages = $this->prepareMessages($chat, $msg, $restart);
        // 删除AI设置
        $chatMessages = array_slice($messages, 1);
        $chat->chat = json_encode($chatMessages);

        $json = $this->prepareJsonPayload($messages);
        $header = $this->prepareHeaders();
        $client = new Client();
        $request = new Request('POST', $this->url, $header, json_encode($json));
        $promise = $client->sendAsync($request, ['stream' => true]);
        $isStreamClosed = false;
        $isCheck = true;

        $promise->then(
            function ($response) use ($chat, &$isStreamClosed) {
                $body = $response->getBody();
                while (!$body->eof()) {
                    if (connection_aborted()) {
                        if (!$isStreamClosed) {
                            $this->streamClose($chat);
                            $isStreamClosed = true;
                        }
                        break;
                    }
                    $res = Utils::readLine($body);
                    $this->handleResponseData($res);
                }
            },
            function ($exception) use (&$isStreamClosed, $uid, $msg, &$isCheck) {
                if (!$isStreamClosed) {
                    $isCheck = false;
                    $this->streamError($exception->getResponse(), $uid, $msg);
                    $isStreamClosed = false;
                }
            }
        )->wait();

        if (!$isStreamClosed) {
            $this->streamClose($chat);
            $isStreamClosed = true;
        }

        if ($isCheck) {
            if ($parmas['model'] == 1) {
                $esService = new ElasticsearchService();
                // 插入关键词到 ES
                $esService->addKeyword($parmas['msg']);
            }
        }
        return 'data: [LOG_ID]:' . $chat->id . "\n\n" . 'data: [DONE]';
    }

    private function getChatLog($chat_id, $uid, $model)
    {
        if ($chat_id) {
            $chat = AiChatLog::where('id', $chat_id)->where('user_id', $uid)->where('model_id', $model)->find();
            if (!$chat) {
                return false;
            }
        } else {
            $chat = new AiChatLog();
            $chat->user_id = $uid;
            $chat->model_id = $model;
            $chat->chat = '[]';
            $chat->save();
        }
        return $chat;
    }

    private function initializeModel($model, $is_deep_reflection = 0)
    {
        switch ($model) {
            case 0:
                $this->url = self::QW_OPEN_URL;
                $this->model = 'deepseek-v3';
                $this->system = '你现在是九界AI咨询助手，来自苏州九界文化传媒公司，是九界AI中的一种，请以九界AI咨询助手的身份进行回答';
                break;
            case 1:
                $this->url = self::QW_OPEN_URL;
                $this->model = $is_deep_reflection ? 'qwq-plus' : 'qwen-max';
                $this->system = '你现在是九界AI搜索，来自苏州九界文化传媒公司，是九界AI中的一种，请以九界AI搜索的身份在互联网上搜索相关答案并返回相关内容，如果用户输入了链接那么请拒绝用户的请求并告知用户我无法直接访问网页';
                $this->search = true;
                break;
            case 2:
                $this->url = self::QW_OPEN_URL;
                $this->model = 'deepseek-v3';
                $this->system = '你现在是九界AI家庭医生助手，来自苏州九界文化传媒公司，是九界AI中的一种，请以九界AI家庭医生的身份进行各种医学知识相关的回答，以中医为主西医为辅';
                break;
            case 3:
                $this->url = self::QW_OPEN_URL;
                $this->model = 'deepseek-v3';
                $this->system = '你现在是九界AI宠物助手，来自苏州九界文化传媒公司，是九界AI中的一种，请以九界AI宠物助手的身份进行各种宠物知识相关回答';
                break;
        }
        $this->system .= '，全程使用简体中文回答，如果回答中有数学相关公式请使用双$符加换行的markdown语法';
    }

    private function prepareMessages($chat, $msg, $restart)
    {
        $messages = [
            [
                'role' => 'system',
                'content' => $this->system
            ]
        ];
        if ($chat->exists()) {
            $chatMsg = json_decode($chat->chat, true);
            if (is_array($chatMsg)) {
                foreach ($chatMsg as $_msg) {
                    $messages[] = $_msg;
                }
            }
        }
        if ($restart == 1) {
            // 重新生成上一句ai的回答，那么就删除最后一句
            array_pop($messages);
        } else {
            $messages[] = [
                'role' => 'user',
                'content' => $msg
            ];
        }
        return $messages;
    }

    private function prepareJsonPayload($messages)
    {
        return [
            'model' => $this->model,
            'messages' => $messages,
            'stream' => true,
            'enable_search' => $this->search
        ];
    }

    private function prepareHeaders()
    {
        return [
            'Authorization' => 'Bearer ' . self::QW_KEY,
        ];
    }

    private function streamClose($chat)
    {
        // 处理流关闭后的逻辑，包括正常结束或者手动终止
        $msg = json_decode($chat->chat, true);
        $msg[] = [
            'role' => 'assistant',
            'reasoning_content' => $this->reasoning_content, // 深度思考的内容
            'content' => $this->chat // 只记录回答的结果
        ];
        $chat->chat = json_encode($msg);
        $chat->save();
        ob_flush();
        flush();
    }

    private function streamError($res, $uid, $msg)
    {
        // 处理流异常后的逻辑
        $error = json_decode($res->getBody()->getContents(), true);
        $errors = [
            'user_id' => $uid,
            'msg' => $msg,
            'error' => $error,
        ];
        $msg = $this->getAliyunErrorMsg($error['error']['code']);
        echo 'data:' . $msg . "\n\n";
        // 追加写入错误日志
        file_put_contents('error.txt', json_encode($errors, JSON_UNESCAPED_UNICODE), FILE_APPEND);
        ob_flush();
        flush();
    }

    private function handleResponseData($data)
    {
        $complete = json_decode($data);
        if (isset($complete->error)) {
            echo 'data:' . $complete->error->code . "\n\n";
            ob_flush();
            flush();
            exit;
        }
        $res = $this->parseData($data);
        $word = is_array($res) ? $res['data'] : $res;

        if (!empty($word)) {
            if ($word == 'data: [DONE]' || $word == 'data: [CONTINUE]') {
                ob_flush();
                flush();
            } else {
                // 将对话保存到变量中
                if (is_array($res)) {
                    $this->reasoning_content .= $word;
                } else {
                    $this->chat .= $word;
                }

                $word = str_replace("\n", '<br/>', $word);
                $word = str_replace(" ", '&nbsp;', $word);

                if (is_array($res)) {
                    $text = json_encode(['type' => 'reasoning_content', 'data' => $word], JSON_UNESCAPED_UNICODE);
                    echo "data:$text\n\n";
                } else {
                    echo "data:$word\n\n";
                }

                ob_flush();
                flush();
            }
        }
    }

    private function parseData($data)
    {
        $data = str_replace('data: {', '{', $data);
        $data = str_replace('data:{', '{', $data);
        $data = rtrim($data, "\n\n");
        if (strpos($data, "}\n\n{") !== false) {
            $arr = explode("}\n\n{", $data);
            $data = "{{$arr[1]}";
        }
        if (strpos($data, 'data: [DONE]') !== false) {
            return 'data: [DONE]';
        } else {
            $data = json_decode($data, true);
            if (!is_array($data)) {
                return '';
            }
            if (isset($data['error'])) {
                echo 'data:' . $this->getAliyunErrorMsg($data['error']['code']) . "\n\n";
                echo 'data: [EXCEPTION]';
                ob_flush();
                flush();
                exit;
            }
            switch ($data['choices']['0']['finish_reason']) {
                case 'stop':
                    return 'data: [DONE]';
                case 'length':
                    return 'data: [CONTINUE]';
            }

            $delta = $data['choices']['0']['delta'];

            // 优先显示深度思考过程
            if (!empty($delta['reasoning_content'])) {
                return ['data' => $delta['reasoning_content']];
            } else {
                return $delta['content'] ?? '';
            }
        }
    }

    public function toImage($parmas, $uid)
    {
        $model = $parmas['model'];
        $prompt = $parmas['prompt'];
        $size = $parmas['size'];
        $n = $parmas['n'];
        $watermark = $parmas['watermark'] == 1 ? true : false;

        $this->url = self::QW_IMAGE_URL;
        switch ($model) {
            case 1:
                $this->model = 'wanx2.1-t2i-turbo';
                break;
            case 2:
                $this->model = 'wanx2.1-t2i-plus';
                break;
        }

        $headers = [
            'X-DashScope-Async' => 'enable',
            'Content-Type' => 'application/json',
            'Authorization' => 'Bearer ' . self::QW_KEY
        ];

        $json = [
            'model' => $this->model,
            'input' => [
                'prompt' => $prompt,
            ],
            'parameters' => [
                'size' => "$size[0]*$size[1]",
                'n' => (int) $n,
                'watermark' => $watermark
            ]
        ];

        $client = new Client();
        try {
            $resp = $client->post($this->url, [
                'headers' => $headers,
                'json' => $json
            ]);
        } catch (GuzzleException $e) {
            $responseBody = $e->getResponse()->getBody()->getContents();
            $responseData = json_decode($responseBody, true);
            $errorCode = $responseData['code'] ?? 'Unknown error';
            $msg = $this->getAliyunErrorMsg($errorCode);
            return JsonServer::error("图片生成失败，$msg");
        }
        $body = $resp->getBody()->getContents();
        $data = json_decode($body, true);
        if (isset($data['output']['task_id'])) {
            // 图片生成中
            AiToWork::create([
                'user_id' => $uid ?? 0,
                'task_id' => $data['output']['task_id'],
                'params' => json_encode($parmas),
                'type' => 1,
                'status' => 0,
            ]);
            return JsonServer::success('图片生成中', $data['output']['task_id']);
        } else {
            return JsonServer::error('图片生成失败，' . $data['message']);
        }
    }

    private function getAliyunErrorMsg($code)
    {
        switch ($code) {
            case 'InvalidParameter':
                return '九界AI服务器错误，请联系客服处理或稍后再试';
            case 'APIConnectionError':
                return '九界AI服务器网络出错，请稍后再试';
            case 'invalid_request_error':
                return '九界AI服务器错误，请联系客服处理或稍后再试';
            case 'DataInspectionFailed':
            case 'data_inspection_failed':
                return '敏感内容，生成失败';
            case 'IPInfringementSuspect':
                return 'IP侵权，生成失败';
            default:
                return '服务错误，请稍后再试';
        }
    }

    private function getTask($task_id, $uid)
    {
        $model = AiToWork::where('task_id', $task_id)->where('user_id', $uid)->find();
        if (!$model) {
            return [
                'output' => [
                    'task_status' => 'NULL',
                    'message' => '任务不存在'
                ]
            ];
        }
        if ($model->status == 1) {
            return [
                'output' => [
                    'task_status' => 'OK',
                    'results' => json_decode($model->work, true)
                ]
            ];
        } else if ($model->status == 2) {
            return [
                'output' => [
                    'task_status' => 'FAILED',
                    'message' => json_decode($model->work, true)['error']
                ]
            ];
        }
        $url = "https://dashscope.aliyuncs.com/api/v1/tasks/$task_id";
        $headers = [
            'Authorization' => 'Bearer ' . self::QW_KEY
        ];
        $client = new Client();
        try {
            $resp = $client->get($url, [
                'headers' => $headers
            ]);
        } catch (GuzzleException $e) {
            $responseBody = $e->getResponse()->getBody()->getContents();
            $responseData = json_decode($responseBody, true);
            $errorCode = $responseData['code'] ?? 'Unknown error';
            $msg = $this->getAliyunErrorMsg($errorCode);
            return [
                'output' => [
                    'task_status' => 'FAILED',
                    'message' => $msg
                ]
            ];
        }
        $body = $resp->getBody()->getContents();
        $body = json_decode($body, true);
        if (isset($body['output']['task_status']) && $body['output']['task_status'] == 'UNKNOWN') {
            $model->work = json_encode([
                'error' => '任务不存在'
            ]);
            $model->status = 2;
            $model->save();
        }
        return $body;
    }

    public function getImage($parmas, $uid)
    {
        $task_id = $parmas['task_id'];
        $data = $this->getTask($task_id, $uid);
        if ($data['output']['task_status'] == 'OK') {
            return JsonServer::success('图片生成成功', [
                'iamge' => $data['output']['results'],
                'image' => $data['output']['results']
            ]);
        } else if ($data['output']['task_status'] == 'SUCCEEDED') {
            // 图片生成成功
            $result = $data['output']['results'];
            $url = [];
            $i = 1;
            foreach ($result as $item) {
                if (isset($item['url'])) {
                    $path = "uploads/ai_images/{$task_id}_$i.png";
                    FileServer::uploadUrl($item['url'], $path);
                } else {
                    $path = "images/jiujie_uni/ai/ai_picture/icon_error.png";
                }
                $url[] = "https://static.jsss999.com/$path";
                $i++;
            }
            // 上传数据库
            $model = AiToWork::where('task_id', $task_id)->find();
            $model->work = json_encode($url);
            $model->status = 1;
            $model->save();

            return JsonServer::success('图片生成成功', [
                'iamge' => $url,
                'image' => $url
            ]);
        } else if ($data['output']['task_status'] == 'FAILED') {
            if (isset($data['output']['code'])) {
                $data['output']['message'] = $this->getAliyunErrorMsg($data['output']['code']);
            }
            // 图片生成失败
            AiToWork::where('task_id', $task_id)->update([
                'work' => json_encode([
                    'error' => $data['output']['message']
                ]),
                'status' => 2
            ]);
            return JsonServer::error('图片生成失败，' . $data['output']['message']);
        } else if ($data['output']['task_status'] == 'RUNNING' || $data['output']['task_status'] == 'PENDING' || $data['output']['task_status'] == 'SUSPENDED') {
            // 图片生成中
            return JsonServer::success('图片生成中', $task_id, 1, 1);
        } else {
            return JsonServer::error('任务不存在');
        }
    }

    public function toVideo($parmas, $uid)
    {
        $to = $parmas['to'];
        $prompt = $parmas['prompt'] ?? '';
        $img_url = $parmas['img_url'] ?? '';
        $trait = $parmas['trait'] ?? [];

        switch ($to) {
            case 1:
                $this->model = 'wanx2.1-i2v-plus';
                break;
            case 2:
                $this->model = 'wanx2.1-t2v-turbo'; // 文生视频 支持 480P 和 720P 对应的所有分辨率。默认分辨率为1280*720（720P）。
                break;
        }

        $this->url = self::QW_VIDEO_URL;
        $headers = [
            'X-DashScope-Async' => 'enable',
            'Content-Type' => 'application/json',
            'Authorization' => 'Bearer ' . self::QW_KEY
        ];
        $input = [];
        if ($prompt) {
            $input['prompt'] = $prompt;
        }
        if ($img_url) {
            $input['img_url'] = $img_url;
        }
        $json = [
            'model' => $this->model,
            'input' => $input
        ];
        $client = new Client();
        try {
            $resp = $client->post($this->url, [
                'headers' => $headers,
                'json' => $json
            ]);
        } catch (GuzzleException $e) {
            $responseBody = $e->getResponse()->getBody()->getContents();
            $responseData = json_decode($responseBody, true);
            $errorCode = $responseData['code'] ?? 'Unknown error';
            $msg = $this->getAliyunErrorMsg($errorCode);
            return JsonServer::error("视频生成失败，$msg");
        }
        $body = $resp->getBody()->getContents();
        $data = json_decode($body, true);
        if (isset($data['output']['task_id'])) {
            // 视频生成中
            AiToWork::create([
                'user_id' => $uid ?? 0,
                'task_id' => $data['output']['task_id'],
                'params' => json_encode([
                    'to' => $to,
                    'prompt' => $prompt,
                    'img_url' => $img_url,
                    'trait' => $trait
                ]),
                'type' => 2,
                'status' => 0,
            ]);
            return JsonServer::success('视频生成中', $data['output']['task_id']);
        } else {
            return JsonServer::error('视频生成失败，' . $data['message']);
        }
    }

    public function getVideo($parmas, $uid)
    {
        $task_id = $parmas['task_id'];
        $data = $this->getTask($task_id, $uid);
        if ($data['output']['task_status'] == 'OK') {
            return JsonServer::success('视频生成成功', ['video' => $data['output']['results']]);
        } else if ($data['output']['task_status'] == 'SUCCEEDED') {
            $model = AiToWork::where('task_id', $task_id)->find();

            if ($model->status == 3) {
                return JsonServer::error('水印正在生成中');
            }
            // 视频生成成功
            if (!empty($data['output']['video_url'])) {
                $result = $data['output']['video_url'];
            } else {
                $result = $data['output']['results']['video_url'] ?? '';
            }
            if (empty($result)) {
                return JsonServer::error('数据错误，请联系管理员');
            }
            //$result = 'https://static-nine-world.oss-cn-shanghai.aliyuncs.com/uploads/ai_videos/17c9fe77-45b7-4079-9661-16ef55811fa6.mp4';
            $localInputVideo = public_path() . "uploads/temp/{$task_id}.mp4";
            // 下载视频到本地
            $this->downloadVideo($result, $localInputVideo);
            $path = "uploads/ai_videos/{$task_id}.mp4";
            $url = [];
            $url[] = "https://static-nine-world.oss-cn-shanghai.aliyuncs.com/$path";

            //视频添加水印
            $paths = "uploads/temp/{$task_id}_" . date('YmdHis') . ".mp4";
            $localOutputVideo = public_path() . $paths;
            // 水印文字内容
            $watermarkImage = public_path() . '/uploads/222.png';
            $model->status = 3;
            $model->save();
            // 构建 FFmpeg 命令，将水印图片叠加到视频右下角
            $command = "ffmpeg -i $localInputVideo -i $watermarkImage -filter_complex \"overlay=W-w-10:H-h-10\" $localOutputVideo";
            // 执行命令
            exec($command, $output, $returnCode);

            if ($returnCode != 0) {
                $model->status = 2;
                $model->save();
                return JsonServer::error('水印添加失败', [], 1, 1);
            }

            FileServer::uploadUrl(public_path() . $paths, $path);
            // 上传数据库
            $model->work = json_encode($url);
            $model->status = 1;
            $model->save();

            unlink($localOutputVideo);
            unlink($localInputVideo);
            return JsonServer::success('视频生成成功', ['video' => $url]);
        } else if ($data['output']['task_status'] == 'FAILED') {
            if (isset($data['output']['code'])) {
                $data['output']['message'] = $this->getAliyunErrorMsg($data['output']['code']);
            }
            // 视频生成失败
            AiToWork::where('task_id', $task_id)->update([
                'work' => json_encode([
                    'error' => $data['output']['message']
                ]),
                'status' => 2
            ]);
            return JsonServer::error('视频生成失败，' . $data['output']['message']);
        } else if ($data['output']['task_status'] == 'RUNNING' || $data['output']['task_status'] == 'PENDING' || $data['output']['task_status'] == 'SUSPENDED') {
            // 视频生成中
            return JsonServer::success('视频生成中', $task_id, 1, 1);
        } else {
            return JsonServer::error('任务不存在');
        }
    }

    /**
     * 下载视频到本地
     * @param string $url 视频链接
     * @param string $filename 本地保存的文件名
     */
    private function downloadVideo($url, $filename)
    {
        $content = file_get_contents($url);
        file_put_contents($filename, $content);
    }

    /**
     * 清理临时文件
     * @param string $inputFile 输入视频文件名
     * @param string $outputFile 输出视频文件名
     */
    private function cleanTempFiles($inputFile, $outputFile)
    {
        Filesystem::disk('local')->delete($inputFile);
        Filesystem::disk('local')->delete($outputFile);
    }


    public function getAiWorkList($parmas, $uid)
    {
        $type = $parmas['type'];
        $page = $parmas['page'];
        $pageSize = 10;
        $model = AiToWork::where('user_id', $uid)->where('status', 'in', [0, 1]);
        if ($type != 3) {
            $model->where('type', $type);
        }
        if (!empty($parmas['close_person_upload'])) {
            $model->whereRaw("TRIM(params) <> '{}'"); // 不展示个人上传的图片和视频
        }
        $model = $model->order('id', 'desc');
        //计算总页数
        $total = $model->count();
        $show = ($total === 0) ? 0 : ceil($total / $pageSize);
        $model = $model->page($page, $pageSize)->select();
        $list = [];
        foreach ($model as $item) {
            $list[] = [
                'task_id' => $item->task_id,
                'params' => json_decode($item->params),
                'type' => $item->type,
                'status' => $item->status,
                'work' => json_decode($item->work)
            ];
        }
        return JsonServer::success('获取成功', [
            'page' => $page,
            'page_count' => $show,
            'total' => $total,
            'list' => $list
        ]);
    }

    public function delAiWork($params, $uid)
    {
        $task_id = $params['task_id'];
        $model = AiToWork::where('task_id', $task_id)->where('user_id', $uid)->find();
        if (!$model) {
            return JsonServer::error('任务不存在');
        }
        $model->delete();
        return JsonServer::success('删除成功');
    }

    public function getUserInfo($uid)
    {
        // 获取元力元气
        $model = UserProfile::where('user_id', $uid)->find();
        $data = [
            'user_info' => [
                'id' => $model->user_id,
                'nickname' => $model->getUser->nickname,
                'avatar' => UrlServer::getFileUrl($model->getUser->avatar),
            ],
            'meta_point' => $model->meta_point ?? 0,
            'meta_energy' => $model->meta_energy ?? 0,
            'user_money' => $model->getUser->user_money ?? 0
        ];
        return JsonServer::success('获取成功', $data);
    }

    public function getHongbaoType($uid)
    {
        $todayStart = date('Y-m-d 00:00:00');
        $todayEnd = date('Y-m-d 23:59:59');
        $model = AiHongbaoLog::where('user_id', $uid)->whereBetween('create_time', [$todayStart, $todayEnd])
            ->order('id', 'desc')->find();
        // 判断是否有红包
        $data = [];
        if ($model) {
            // 判断是否是两小时内的
            if (time() - strtotime($model->create_time) < 7200) {
                $data[] = [
                    'hongbao_id' => $model->hongbao_id,
                    'money' => $model->money,
                    'type' => $model->type,
                    'time' => time() - strtotime($model->create_time)
                ];
            }
        }
        return JsonServer::success('OK', $data);
    }

    public function openHongbao($uid, $id)
    {
        $time = time();
        $todayStart = date('Y-m-d 00:00:00');
        $todayEnd = date('Y-m-d 23:59:59');
        $day = AiHongbaoLog::where('user_id', $uid)->whereBetween('create_time', [$todayStart, $todayEnd])->order('id', 'desc')->find();
        $model = AiHongbao::find(2);
        // 判断$day->create_time是否过了$model->time_interval小时
        if ($day && $time - strtotime($day->create_time) < $model->time_interval * 3600) {
            $remainingSeconds = $model->time_interval * 3600 - ($time - strtotime($day->create_time));
            $remainingHours = floor($remainingSeconds / 3600);
            $remainingMinutes = floor(($remainingSeconds % 3600) / 60);

            $message = "";
            if ($remainingHours > 0) {
                $message .= "{$remainingHours}小时";
            }
            if ($remainingMinutes > 0) {
                $message .= "{$remainingMinutes}分钟";
            }
            $message .= "后才能开启下一个红包";

            return JsonServer::error($message);
        }
        $odds = json_decode($model->odds, true);
        $raw = AiMedicalLogic::newRaffle($odds);
        if ($raw['props'] == 3 && $raw['money'] > 12.88) {
            // 判断大奖是否抽光
            if ($model->gp_limit < 1) {
                $raw['money'] = 8.88;
            } else {
                $model->gp_limit -= 1;
                $model->save();
            }
        }
        // 新增日志
        AiHongbaoLog::create([
            'user_id' => $uid,
            'hongbao_id' => $id,
            'money' => $raw['money'],
            'type' => $raw['props']
        ]);
        $this->raw($uid, $raw, 'AI拼手气红包');
        return JsonServer::success('OK', $raw);
    }

    public function raw($uid, $raw, $notes)
    {
        $profile = UserProfile::where('user_id', $uid)->find();
        switch ($raw['props']) {
            case '1':
                // 元力
                $profile->meta_point += $raw['money'];
                // 元力日志
                $point_data['user_id'] = $uid;
                $point_data['from_user_id'] = $uid;
                $point_data['meta_point'] = $raw['money'];
                $point_data['type'] = 2;
                $point_data['to_user_id'] = 0;
                $point_data['account_type'] = 1;
                $point_data['extra_info'] = $notes;
                $point_data['created_at'] = Carbon::now()->toDateTimeString();
                UserMetaPointLog::create($point_data);
                break;
            case '2':
                // 元气
                $profile->meta_energy += $raw['money'];
                break;
            case '3':
                $user = User::find($uid);
                $user->user_money += $raw['money'];
                $user->save();
                // 日志
                AccountLogLogic::AccountRecord($uid, $raw['money'], 1, AccountLog::hongbao, $notes);
                break;
            default:
                return true;
        }
        $profile->save();
        return true;
    }

    public function getHongbaoRank($uid, $page)
    {
        $pageSize = 10;
        $model = AiHongbaoRank::withJoin([
            'getUser' => ['nickname', 'avatar']
        ])->order('asset', 'desc')
            ->visible(['money', 'point', 'energy', 'asset', 'getUser']);
        //计算总页数
        $total = $model->count();
        $show = ($total === 0) ? 0 : ceil($total / $pageSize);
        $model = $model->page($page, $pageSize)->select();
        $rank = null;
        $asset = null;
        $iModel = new stdClass;
        $iModel->money = null;
        $iModel->point = null;
        $iModel->energy = null;
        if ($uid && AiHongbaoRank::where('user_id', $uid)->find()) {
            // 计算自己所处的排名
            $iModel = AiHongbaoRank::where('user_id', $uid)->find();
            $asset = $iModel->asset;
            $rank = AiHongbaoRank::where('asset', '>', $asset)->count() + 1;
        }
        foreach ($model as &$item) {
            $item->getUser->avatar = UrlServer::getFileUrl($item->getUser->avatar);
        }
        return JsonServer::success('获取成功', [
            'page' => $page,
            'page_count' => $show,
            'total' => $total,
            'rank' => $rank,
            'asset' => $asset,
            'money' => $iModel->money,
            'point' => $iModel->point,
            'energy' => $iModel->energy,
            'list' => $model
        ]);
    }

    public function getHongbaoRand()
    {
        $date = date('Y-m-d', time());
        $gp = AiHongbao::find(1)->gp_limit;
        $logs = AiHongbaoLog::withJoin([
            'getUser' => ['nickname', 'avatar']
        ])->where('ai_hongbao_log.create_time', 'like', "$date%")
            ->where('ai_hongbao_log.money', '>', 50)
            ->order('ai_hongbao_log.id', 'desc')
            ->limit(20)
            ->select()
            ->visible(['money', 'type', 'getUser']);
        foreach ($logs as &$item) {
            $item->money = rtrim(rtrim($item->money, '0'), '.');
            $item->getUser->avatar = UrlServer::getFileUrl($item->getUser->avatar);
        }
        return JsonServer::success('OK', [
            'gp_limit' => $gp,
            'rand' => $logs
        ]);
    }

    public function exEnergy($uid, $parmas)
    {
        $money = $parmas['money'];
        $scene = $parmas['scene'];
        $profile = UserProfile::where('user_id', $uid)->find();
        if ($scene == 1) {
            // 余额兑换
            $model = User::find($uid);
            $key = 'user_money';
            $energy = $money * 100;
            // 余额日志
            AccountLogLogic::AccountRecord($uid, $money, 2, AccountLog::exchange, '元气兑换');
        } else {
            // 元力兑换
            $model = $profile;
            $key = 'meta_point';
            $energy = $money * 10;
            // 元力日志
            $point_data['user_id'] = $uid;
            $point_data['from_user_id'] = $uid;
            $point_data['meta_point'] = $money;
            $point_data['type'] = 3;
            $point_data['to_user_id'] = 0;
            $point_data['account_type'] = 1;
            $point_data['extra_info'] = '元气兑换';
            $point_data['created_at'] = Carbon::now()->toDateTimeString();
            UserMetaPointLog::create($point_data);
        }
        if ($model->$key < $money) {
            return JsonServer::error('余额不足');
        }
        $model->$key -= $money;
        $profile->meta_energy += $energy;
        $model->save();
        $profile->save();
        return JsonServer::success('兑换成功');
    }

    public function setAcl($path, $acl = 'public-read')
    {
        $config = [
            'default' => ConfigServer::get('storage', 'default', 'local'),
            'engine' => ConfigServer::get('storage_engine') ?? ['local' => []]
        ];
        $StorageDriver = new Driver($config);
        if ($StorageDriver->setAcl($path, $acl)) {
            return JsonServer::success('设置成功');
        } else {
            return JsonServer::error('设置失败');
        }
    }

    public function getPorpsNum($uid)
    {
        $data = [
            'x2' => GamesUserBag::where('user_id', $uid)->where('prop_id', 144)->value('prop_num') ?? 0,
            'x3' => GamesUserBag::where('user_id', $uid)->where('prop_id', 145)->value('prop_num') ?? 0,
            'x5' => GamesUserBag::where('user_id', $uid)->where('prop_id', 146)->value('prop_num') ?? 0,
            'double' => GamesUserBag::where('user_id', $uid)->where('prop_id', 147)->value('prop_num') ?? 0,
            'boom' => GamesUserBag::where('user_id', $uid)->where('prop_id', 149)->value('prop_num') ?? 0,
        ];
        return JsonServer::success('获取成功', $data);
    }

    public function speedHongbaoStart($uid, $porps)
    {
        $todayStart = date('Y-m-d 00:00:00');
        $todayEnd = date('Y-m-d 23:59:59');
        $log = AiSpeedHongbaoLog::where('user_id', $uid)->where('status', 1)->whereBetween('create_time', [$todayStart, $todayEnd])->order('id', 'desc')->find();
        // 判断是否超过12小时
        if ($log && time() - strtotime($log->create_time) < 12 * 3600) {
            return JsonServer::error('请等待12小时后再试');
        }
        // 判断是否有使用道具
        if ($porps['x2'] > 0) {
            // 使用了x2
            $x2 = GamesUserBag::where('user_id', $uid)->where('prop_id', 144)->find();
            if ($x2->prop_num < 1) {
                return JsonServer::error('x2道具不足');
            }
            $x2->prop_num -= 1;
        }
        if ($porps['x3'] > 0) {
            // 使用了x3
            $x3 = GamesUserBag::where('user_id', $uid)->where('prop_id', 145)->find();
            if ($x3->prop_num < 1) {
                return JsonServer::error('x3道具不足');
            }
            $x3->prop_num -= 1;
        }
        if ($porps['x5'] > 0) {
            // 使用了x5
            $x5 = GamesUserBag::where('user_id', $uid)->where('prop_id', 146)->find();
            if ($x5->prop_num < 1) {
                return JsonServer::error('x5道具不足');
            }
            $x5->prop_num -= 1;
        }
        if ($porps['double'] > 0) {
            // 使用了double
            $double = GamesUserBag::where('user_id', $uid)->where('prop_id', 147)->find();
            if ($double->prop_num < 1) {
                return JsonServer::error('double道具不足');
            }
            $double->prop_num -= 1;
        }
        $model = AiSpeedHongbao::select();
        $data = [];
        foreach ($model as $item) {
            $rew = json_decode($item->odds, true);
            $money = 0;
            $type = 1;
            if ($rew['energy'] > 0) {
                // 判断元气是否是数组
                if (is_array($rew['energy'])) {
                    $money = mt_rand($rew['energy'][0], $rew['energy'][1]);
                } else {
                    $money = $rew['energy'];
                }
            } else {
                $type = 2;
                $money = $rew['point'];
            }
            if ($porps['double'] > 0) {
                $money *= 2;
            }
            $data[] = [
                'money' => $money,
                'type' => $type,
                'count' => $item->count
            ];
        }
        if (!empty($x2)) {
            $x2->save();
        }
        if (!empty($x3)) {
            $x3->save();
        }
        if (!empty($x5)) {
            $x5->save();
        }
        if (!empty($double)) {
            $double->save();
        }
        $i = 1;
        foreach ($data as &$item) {
            if ($i > 10) {
                $rand = mt_rand(0, 10);
                if ($i > 30) {
                    if ($rand < 8) {
                        $item['money'] = 0;
                        $item['type'] = 3;
                    }
                } elseif ($i > 20) {
                    if ($rand < 5) {
                        $item['money'] = 0;
                        $item['type'] = 3;
                    }
                } else {
                    if ($rand < 3) {
                        $item['money'] = 0;
                        $item['type'] = 3;
                    }
                }
            }
            $i++;
        }

        // 将之前的记录改为已结束
        AiSpeedHongbaoLog::where('user_id', $uid)->where('status', 0)->update([
            'status' => 1
        ]);

        $speed = new AiSpeedHongbaoLog;
        $speed->user_id = $uid;
        $speed->count = 0;
        $speed->porp = json_encode($porps);
        $speed->odds = json_encode($data);
        $speed->save();
        return JsonServer::success('开始抽奖', $data);
    }

    public function buySpeedBoom($uid, $type, $num)
    {
        $profile = UserProfile::where('user_id', $uid)->find();
        if ($type == 1) {
            $money = 100;
            $key = 'meta_point';
        } else {
            $money = 10000;
            $key = 'meta_energy';
        }
        if ($profile->$key < $money * $num) {
            return JsonServer::error('余额不足');
        }
        $profile->$key -= $money * $num;
        if ($type == 1) {
            // 元力日志
            $point_data['user_id'] = $uid;
            $point_data['from_user_id'] = $uid;
            $point_data['meta_point'] = $money * $num;
            $point_data['type'] = 9;
            $point_data['to_user_id'] = 0;
            $point_data['account_type'] = 2;
            $point_data['extra_info'] = '购买解密钥匙';
            $point_data['created_at'] = Carbon::now()->toDateTimeString();
            UserMetaPointLog::create($point_data);
        }
        $profile->save();
        $bag = GamesUserBag::where('user_id', $uid)->where('prop_id', 149)->find();
        if ($bag) {
            $bag->prop_num += $num;
            $bag->save();
            $num = $bag->prop_num;
        } else {
            GamesUserBag::create([
                'user_id' => $uid,
                'prop_id' => 149,
                'prop_num' => $num
            ]);
        }
        return JsonServer::success('购买成功', ['num' => $num]);
    }

    public function useSpeedBoom($uid)
    {
        $bag = GamesUserBag::where('user_id', $uid)->where('prop_id', 149)->find();
        if (!$bag) {
            return JsonServer::error('炸弹不足');
        }
        if ($bag->prop_num < 1) {
            return JsonServer::error('炸弹不足');
        }
        $bag->prop_num -= 1;
        $bag->save();
        return JsonServer::success('使用成功', ['num' => $bag->prop_num]);
    }

    public function speedHongbaoEnd($uid, $count)
    {
        $todayStart = date('Y-m-d 00:00:00');
        $todayEnd = date('Y-m-d 23:59:59');
        $log = AiSpeedHongbaoLog::where('user_id', $uid)->where('status', 0)->whereBetween('create_time', [$todayStart, $todayEnd])->order('id', 'desc')->find();
        if (!$log) {
            return JsonServer::error('请先开始抽奖');
        }
        // 判断是否超过12小时
        if (time() - strtotime($log->create_time) > 12 * 3600) {
            return JsonServer::error('请等待12小时后再试');
        }
        $porp = json_decode($log->porp, true);
        $x2 = $porp['x2'] ?? 0;
        $x3 = $porp['x3'] ?? 0;
        $x5 = $porp['x5'] ?? 0;
        $double = $porp['double'] ?? 0;
        $s = $x2 * 2 + $x3 * 3 + $x5 * 5;
        if ($s == 0) {
            $s = 1;
        }
        // 判断有没有作弊
        if ($count > $s * 1000) {
            if ($s >= 10 && $count > 9000) {
                // 这个不算作弊
            } else {
                return JsonServer::error('您作弊了！');
            }
        }
        $data = json_decode($log->odds, true);
        $rew = [
            'point' => 0,
            'energy' => 0
        ];
        $log->count = $count;
        foreach ($data as $item) {
            if ($count < $item['count']) {
                break;
            }
            $count -= $item['count'];
            // if ($double == 1) {
            //     // 奖励翻倍
            //     $item['money'] *= 2;
            // }
            // 开始领取奖励
            if ($item['type'] == 1) {
                // 元气
                $this->raw($uid, [
                    'props' => 2,
                    'money' => $item['money']
                ], 'AI手速红包');
                $rew['energy'] += $item['money'];
            } elseif ($item['type'] == 2) {
                // 元力
                $this->raw($uid, [
                    'props' => 1,
                    'money' => $item['money']
                ], 'AI手速红包');
                $rew['point'] += $item['money'];
            }
        }
        $log->reward = json_encode($rew);
        $log->status = 1;
        $log->save();

        return JsonServer::success('领取成功', $rew);
    }

    public function decodeHongbaoCount($uid)
    {
        $todayStart = date('Y-m-d 00:00:00');
        $todayEnd = date('Y-m-d 23:59:59');
        // count为0代表3次，count为1代表2次，count为2代表1次
        $count = AiDecodeHongbaoLog::where('user_id', $uid)->where('status', 1)->where('type', 1)->whereBetween('create_time', [$todayStart, $todayEnd])->order('id', 'desc')->count();
        $count++;
        return JsonServer::success('OK', ['count' => $count]);
    }

    public function decodeHongbaoStart($uid)
    {
        $todayStart = date('Y-m-d 00:00:00');
        $todayEnd = date('Y-m-d 23:59:59');
        $count = AiDecodeHongbaoLog::where('user_id', $uid)->where('status', 1)->where('type', 1)->whereBetween('create_time', [$todayStart, $todayEnd])->order('id', 'desc')->count();
        $num = [];
        $list = 3;
        switch ($count) {
            case 0:
                // 3位
                $list = 3;
                $reward = 1;
                break;
            case 1:
                // 4位
                $list = 4;
                $reward = 1;
                break;
            case 2:
                // 5位
                $list = 5;
                $reward = 2;
                break;
            case 3:
                // 6位
                $list = 6;
                $reward = 2;
                break;
            case 4:
                // 7位
                $list = 7;
                $reward = 3;
                break;
            case 5:
                // 8位
                $list = 8;
                $reward = 3;
                break;
            case 6:
                // 9位
                $list = 9;
                $reward = 4;
                break;
            default:
                // 10位
                $list = 10;
                $reward = 5;
                break;
        }
        // 随机list个数字，要求每个数字不重复且可以以0开头
        for ($i = 0; $i < $list; $i++) {
            $rand = mt_rand(0, 9);
            if ($i == 0) {
                $num[] = $rand;
            } else {
                while (in_array($rand, $num)) {
                    $rand = mt_rand(0, 9);
                }
                $num[] = $rand;
            }
        }
        $num = implode('', $num);
        $model = new AiDecodeHongbaoLog;
        $model->user_id = $uid;
        $model->topic = $num;
        $model->reward = $reward;
        $model->count = $count + 1;

        // $key = "wqrhgblaf2312gva"; // 16字节密钥
        // $iv = "guy134hna9fgkl12"; // 16字节IV

        // // 加密
        // $encrypted = openssl_encrypt($num, 'AES-128-CBC', $key, OPENSSL_RAW_DATA, $iv);
        // $num = base64_encode($encrypted);

        $num = (new AesServer)->encrypt($num);
        if ($model->save()) {
            return JsonServer::success('OK', ['topic' => $num]);
        }
    }

    public function decodeHongbaoEnd($uid, $answer, $timer)
    {
        $answer = (new AesServer)->decrypt($answer);
        if ($answer === false) {
            return JsonServer::error('禁止作弊！！！');
        }
        $todayStart = date('Y-m-d 00:00:00');
        $todayEnd = date('Y-m-d 23:59:59');
        $log = AiDecodeHongbaoLog::where('user_id', $uid)->where('status', 0)->whereBetween('create_time', [$todayStart, $todayEnd])->order('id', 'desc')->find();
        if (!$log) {
            return JsonServer::error('请先开始游戏');
        }
        $log->status = 1;
        $log->answer = $answer;
        $log->type = 0;
        $log->timer = $timer;
        // 拆分$answer为数组
        $answer = str_split($answer);
        $topic = str_split($log->topic);
        $i = 0;
        $porps = GamesUserBag::where('user_id', $uid)->where('prop_id', 148)->find();
        foreach ($topic as $item) {
            if (!isset($answer[$i])) {
                $log->save();
                return JsonServer::error('回答错误');
            }
            if ($answer[$i] == '*') {
                if (empty($porps) || $porps->prop_num < 1) {
                    $log->save();
                    return JsonServer::error('钥匙不足');
                }
                $porps->prop_num -= 1;
                $porps->save();
            } else {
                if ($item != $answer[$i]) {
                    $log->save();
                    return JsonServer::error('回答错误');
                }
            }
            $i++;
        }
        $log->type = 1;
        // 领取奖励
        $this->raw($uid, [
            'props' => 1,
            'money' => $log->reward
        ], 'AI解密红包');
        $log->save();
        return JsonServer::success('领取成功', ['reward' => $log->reward]);
    }

    public function buyDecodeKey($uid, $type, $num)
    {
        $profile = UserProfile::where('user_id', $uid)->find();
        if ($type == 1) {
            $money = 100;
            $key = 'meta_point';
        } else {
            $money = 10000;
            $key = 'meta_energy';
        }
        if ($profile->$key < $money * $num) {
            return JsonServer::error('余额不足');
        }
        $profile->$key -= $money * $num;
        if ($type == 1) {
            // 元力日志
            $point_data['user_id'] = $uid;
            $point_data['from_user_id'] = $uid;
            $point_data['meta_point'] = $money * $num;
            $point_data['type'] = 9;
            $point_data['to_user_id'] = 0;
            $point_data['account_type'] = 2;
            $point_data['extra_info'] = '购买解密钥匙';
            $point_data['created_at'] = Carbon::now()->toDateTimeString();
            UserMetaPointLog::create($point_data);
        }
        $profile->save();
        $bag = GamesUserBag::where('user_id', $uid)->where('prop_id', 148)->find();
        if ($bag) {
            $bag->prop_num += $num;
            $bag->save();
            $num = $bag->prop_num;
        } else {
            GamesUserBag::create([
                'user_id' => $uid,
                'prop_id' => 148,
                'prop_num' => $num
            ]);
        }
        return JsonServer::success('购买成功', ['num' => $num]);
    }

    public function getDecodeKey($uid)
    {
        $bag = GamesUserBag::where('user_id', $uid)->where('prop_id', 148)->find();
        if ($bag) {
            return JsonServer::success('OK', ['num' => $bag->prop_num]);
        } else {
            return JsonServer::success('OK', ['num' => 0]);
        }
    }

    public function getDecodeRand($uid)
    {
        // 获取排行榜，取每人最高关卡的最短用时，取前10名
        $subQuery = AiDecodeHongbaoLog::where('status', 1)
            ->where('type', 1)
            ->group('user_id')
            ->field(['user_id', 'max(id)' => 'max_id'])
            ->buildSql();

        $logs = AiDecodeHongbaoLog::alias('a')
            ->join([$subQuery => 'b'], 'a.id = b.max_id')
            ->with([
                'getUser' => function ($query) {
                    $query->field(['id', 'nickname', 'avatar']);
                }
            ])
            ->order('a.count', 'desc')
            ->order('a.timer', 'asc')
            ->limit(10)
            ->field(['a.timer', 'a.count', 'a.user_id'])
            ->select();

        foreach ($logs as &$item) {
            $item->getUser->avatar = UrlServer::getFileUrl($item->getUser->avatar);
        }

        // 如果uid存在，计算自己的排名
        // $userRank = null;
        // if ($uid) {
        //     $userLog = AiDecodeHongbaoLog::where('user_id', $uid)
        //         ->where('status', 1)
        //         ->where('type', 1)
        //         ->order('count', 'desc')
        //         ->order('timer', 'asc')
        //         ->find();

        //     if ($userLog) {
        //         $userRank = AiDecodeHongbaoLog::alias('a')
        //             ->join([$subQuery => 'b'], 'a.id = b.max_id')
        //             ->where('a.count', '>=', $userLog->count)
        //             ->where('a.timer', '<=', $userLog->timer)
        //             ->count();
        //         $userRank++;
        //     }
        // }

        return JsonServer::success('获取成功', [
            // 'rank' => $userRank,
            'list' => $logs
        ]);
    }

    public function consumeEnergy($uid, $money)
    {
        // 消耗元气
        $model = UserProfile::where('user_id', $uid)->find();
        if ($model->meta_energy < $money) {
            return JsonServer::error('元气不足');
        }
        $model->meta_energy -= $money;
        $model->save();
        return JsonServer::success('OK');
    }

    public function getTheaterList($params)
    {
        $type = $params['type'];
        $page = $params['page'];
        $where = [
            'type' => $type,
            'status' => 1
        ];
        $pageSize = 10;
        $model = AiTheaterModel::where($where)->order('id', 'desc');
        //计算总页数
        $total = $model->count();
        $show = ($total === 0) ? 0 : ceil($total / $pageSize);
        $model = $model->page($page, $pageSize)->select();
        foreach ($model as &$item) {
            $item->url = UrlServer::getFileUrl($item->url);
        }
        return JsonServer::success('获取成功', [
            'page' => $page,
            'page_count' => $show,
            'total' => $total,
            'list' => $model
        ]);
    }

    public static function getAdver(string $keyword)
    {
        try {
            $adver_arr = self::get_adver($keyword);
        } catch (\Throwable $th) {
            $adver_arr = [];
        }
        if (!empty($adver_arr)) {
            $source = array_column($adver_arr, '_source');
            $ad_ids = array_column($source, 'ad_id');

            // 优先按es的匹配度来排序，同一个关键词内绑定的广告，按数据库的sort字段 从大道小 排序
            $adver = [];
            foreach ($ad_ids as $value) {
                if (count($adver) >= 3) { // 只取3个广告
                    break;
                }

                // 当前：不限制status值，后台操作禁用，到定时任务执行时，结束广告的投放，如果需要立马下架广告，可以删除广告，将不再投放
                $temp = AdvertisementLogic::getByIds($value, [], 'sort desc,id asc');
                if (!empty($temp)) {
                    $adver = array_merge($adver, $temp);
                }
            }

            $num = 0;
            foreach ($adver as $value) {
                if ($num > 2) {
                    break;
                }

                $res_json = json_encode([
                    'title' => $value['title'],
                    'link' => $value['link'],
                    'content' => $value['content'],
                    'sort' => $value['sort'],
                ], JSON_UNESCAPED_UNICODE);
                echo 'data:' . $res_json;

                ob_flush();
                flush();
                $num++;
            }
        }
    }

    public static function get_adver($keyword)
    {
        if (empty($keyword)) {
            return [];
        }
        $esService = new ElasticsearchService();

        // 查询广告的关联结果
        $suggestions = $esService->searchKeywords($keyword, AdvertisementLogic::AI_INDEX_NAME);

        return $suggestions;
    }

    public static function get_weather($city_code)
    {
        $key = 'b6c893c236df192b14cf709353214987';

        $url = 'https://restapi.amap.com/v3/weather/weatherInfo?city=' . $city_code . '&key=' . $key;

        $client = new Client();
        $res = $client->get($url);

        $body = $res->getBody()->getContents();
        $data = json_decode($body, true);

        $weather = (object) [];
        if (!empty($data['lives'][0])) {
            $weather = $data['lives'][0];
        }

        return JsonServer::success('获取成功', $weather);
    }

    /**
     * 手动添加 1new9j_ai_to_work 表的数据
     * @param mixed $url
     * @param mixed $type
     * @param mixed $uid
     */
    public static function manuall_add($url, $type, $uid)
    {
        if (!is_array($url)) {
            $url = [$url];
        }
        $insert = [
            'user_id' => $uid,
            'task_id' => self::createUUID(),
            'params' => '{}',
            'work' => json_encode($url),
            'type' => $type,
            'status' => 1,
            'create_time' => date('Y-m-d H:i:s')
        ];
        $res = AiToWork::create($insert);
        if (!$res) {
            return JsonServer::error('添加失败');
        }

        return JsonServer::success('添加成功');
    }

    public function virtual_human_broadcasting($img_url, $audio_url, $uid)
    {
        // 虚拟人播报
        $res = self::check_human_face($img_url);
        if (empty($res['pass'])) {
            $msg = $res['message'] ?? '图片检测失败';
            return JsonServer::error($msg);
        }

        // 生成视频
        $res = self::voice_announcements($img_url, $audio_url);
        if (!$res['res']) {
            return JsonServer::error('视频生成失败');
        }

        // 视频生成中
        AiToWork::create([
            'user_id' => $uid ?? 0,
            'task_id' => $res['task_id'],
            'params' => json_encode([
                'to' => 1,
                'prompt' => '',
                'img_url' => $img_url
            ]),
            'type' => 2,
            'status' => 0,
        ]);

        return JsonServer::success('视频生成中', ['task_id' => $res['task_id']]);
    }

    /**
     * 检测人脸
     * @param mixed $image_url
     */
    public static function check_human_face(string $image_url)
    {
        $client = new Client();
        $url = self::QW_VIDEO_URL_FACE_DETECT;

        $headers = [
            'Content-Type' => 'application/json',
            'Authorization' => 'Bearer ' . self::QW_KEY
        ];

        $json = [
            'model' => 'liveportrait-detect',
            'input' => [
                'image_url' => $image_url
            ]
        ];

        $resp = $client->post($url, [
            'headers' => $headers,
            'json' => $json
        ]);

        $body = $resp->getBody()->getContents();
        $data = json_decode($body, true);

        if (isset($data['output'])) {
            return $data['output'];
        }

        return ['pass' => false, 'message' => '图片检测失败'];
    }

    /**
     * 语音播报
     * @param string $image_url
     */
    public static function voice_announcements(string $image_url, string $audio_url): array
    {
        $client = new Client();
        $url = self::QW_VIDEO_URL_FACE_SYNTHESIS;

        $headers = [
            'X-DashScope-Async' => 'enable',
            'Content-Type' => 'application/json',
            'Authorization' => 'Bearer ' . self::QW_KEY
        ];

        // 使用 getimagesize() 获取完整信息
        $imageInfo = getimagesize($image_url);
        if ($imageInfo === false) {
            throw new Exception("图片无法识别");
        }

        $width = $imageInfo[0]; // 宽度
        $height = $imageInfo[1]; // 高度

        // 图像文件<10M，宽高比≤2，最大边长≤4096。
        // 格式支持：jpeg、jpg、png、bmp、webp。
        $len_max = max($width, $height);
        $len_min = min($width, $height);
        if ($len_max > 4096) {
            throw new Exception("图片最大边长4096");
        }

        if (($len_min * 2) < $len_max) {
            throw new Exception("图片宽高比应小于2");
        }

        // 检查文件扩展名
        $extension = pathinfo($image_url, PATHINFO_EXTENSION);
        $extension = strtolower($extension);
        $supported_formats = ['jpeg', 'jpg', 'png', 'bmp', 'webp'];
        if (!in_array($extension, $supported_formats)) {
            throw new Exception("图片格式仅支持jpeg、jpg、png、bmp、webp");
        }

        // 对于 WebP 格式，额外检查 PHP 环境支持
        if ($extension === 'webp' && !function_exists('imagecreatefromwebp')) {
            throw new Exception("当前不支持WebP格式图片处理");
        }

        $parameters = [
            "template_id" => "normal", // 可按模板控制人物头部的运动姿态和幅度，当前支持3种模板：normal、calm、active。默认为normal。
            "eye_move_freq" => 0.5, // 每秒眨眼次数，可设值为0-1，值越大眨眼频率越高。默认值为0.5。
            "video_fps" => 30, // 输出视频帧率，可设值为15-30。默认值为24。
            "mouth_move_strength" => 1, // 嘴部动作的幅度大小，可设值为0-1.5，值越大嘴型越大。若设为0则嘴部无动作。默认值为1。
            "paste_back" => true, // 生成的人脸是否贴回原图，可设值为true或false。若设为false则仅输出生成的人脸，忽略人物身体。默认值为true
            "head_move_strength" => 0.7 // 头部动作幅度，可设值为0-1，值越大头部动作幅度越大。默认值为0.7。
        ];

        $json = [
            'model' => 'liveportrait',
            'input' => [
                'image_url' => $image_url,
                'audio_url' => $audio_url,
            ],
            'parameters' => $parameters
        ];

        $resp = $client->post($url, [
            'headers' => $headers,
            'json' => $json
        ]);

        $body = $resp->getBody()->getContents();
        $data = json_decode($body, true);

        if (isset($data['output']['task_id'])) {
            return [
                'res' => true,
                'task_id' => $data['output']['task_id'],
            ];
        }

        return ['res' => false];
    }

    /**
     * 识别图片
     */
    public static function identify_images($params)
    {
        $qwurl = self::QW_OPEN_URL;

        $params['model'] = self::QWEN_VL_MAX; // 单图 视觉理解

        $json = self::prepareJson($params);

        $headers = [
            'Content-Type' => 'application/json',
            'Authorization' => 'Bearer ' . self::QW_KEY
        ];

        $client = new Client();

        $res = $client->post($qwurl, [
            'headers' => $headers,
            'json' => $json
        ]);

        $body = $res->getBody()->getContents();
        $data = json_decode($body, true);

        return $data['choices'][0]['message']['content'] ?? '';
    }

    private static function prepareJson($params): array
    {
        $qwmodel = $params['model'];

        $aiContent = '你是一个强大的图片识别助手，请识别图片中心的主要内容，用不超过15个字描述，只描述一个主要物体，忽略环境';

        $content = [];
        if (!empty($params['image'])) {
            if (is_array($params['image'])) {
                foreach ($params['image'] as $value) {
                    $content[] = [
                        "type" => "image_url",
                        "image_url" => ['url' => $value]
                    ];
                }
            } else {
                $content[] = [
                    "type" => "image_url",
                    "image_url" => ['url' => $params['image']]
                ];
            }
        }

        $json = [
            "model" => $qwmodel,
            "messages" => [
                [
                    "role" => "system",
                    "content" => [
                        [
                            "type" => 'text',
                            "text" => $aiContent
                        ],
                    ]
                ],
                [
                    "role" => "user",
                    "content" => $content
                ]
            ]
        ];

        return $json;
    }

    /**
     * 用关键词搜索图片 及 图片信息
     */
    public static function search_keyword_image_text($keyword)
    {
        $url = 'https://cn.bing.com/images/search?q=' . urlencode($keyword) . '&form=HDRSC2';
        $html = file_get_contents($url);
        if (!$html) {
            return json(['code' => 2, 'msg' => '请求必应失败']);
        }

        // 创建DOMDocument对象
        $dom = new \DOMDocument();
        // 禁用错误报告，因为HTML可能不完全符合标准
        libxml_use_internal_errors(true);
        $dom->loadHTML($html);
        libxml_clear_errors();

        $results = [];

        // 获取所有的<li>元素
        $liElements = $dom->getElementsByTagName('li');

        foreach ($liElements as $li) {
            // 检查是否是图片结果项
            if ($li->hasAttribute('data-idx')) {
                $item = [];

                // 1. 提取class="mimg"的img标签的src属性值
                $mimgElements = $li->getElementsByTagName('img');
                foreach ($mimgElements as $img) {
                    if ($img->hasAttribute('class') && strpos($img->getAttribute('class'), 'mimg') !== false) {
                        $src = $img->getAttribute('src');
                        if (empty($src)) {
                            $src = $img->getAttribute('data-src');
                        }
                        if (empty($src)) {
                            continue;
                        }
                        $item['image_src'] = $src;
                        break;
                    }
                }

                // 2. 提取<div class="img_info hon">标签下的a链接的href属性值
                $imgInfoElements = $li->getElementsByTagName('div');
                foreach ($imgInfoElements as $div) {
                    if ($div->hasAttribute('class') && $div->getAttribute('class') === 'img_info hon') {
                        $aElements = $div->getElementsByTagName('a');
                        if ($aElements->length > 0) {
                            $item['link_href'] = $aElements->item(0)->getAttribute('href');
                        }
                        break;
                    }
                }

                // 3. 提取<div class="infnmpt">标签下的a标签中的文本值
                $infnmptElements = $li->getElementsByTagName('div');
                foreach ($infnmptElements as $div) {
                    if ($div->hasAttribute('class') && $div->getAttribute('class') === 'infnmpt') {
                        $aElements = $div->getElementsByTagName('a');
                        if ($aElements->length > 0) {
                            $title_text = trim($aElements->item(0)->getAttribute('title'));
                            $title_text = str_replace('…', '', $title_text);
                            $title_text = str_replace(' ', '', $title_text);
                            $item['title_text'] = $title_text;
                        }
                        break;
                    }
                }

                // 只有当三项信息都找到时才添加到结果中
                if (isset($item['image_src']) && isset($item['link_href']) && isset($item['title_text'])) {
                    $results[] = $item;
                }
            }
        }

        return $results;
    }
}