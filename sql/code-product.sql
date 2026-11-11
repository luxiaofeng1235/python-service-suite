-- ============================================================
-- 电商商品 Agent 演示系统 - 完整 10 类目 & 50 商品数据库脚本
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 1. 类目表 (支持无限级/二级分类)
DROP TABLE IF EXISTS `categories`;
CREATE TABLE `categories` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '类目ID',
  `name` VARCHAR(50) NOT NULL COMMENT '类目名称',
  `parent_id` BIGINT UNSIGNED DEFAULT NULL COMMENT '父级类目ID (NULL表示一级大类)',
  `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序权重',
  PRIMARY KEY (`id`),
  KEY `idx_parent_id` (`parent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品类目表';

-- 2. 商品 SPU 表
DROP TABLE IF EXISTS `products`;
CREATE TABLE `products` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'SPU ID',
  `category_id` BIGINT UNSIGNED NOT NULL COMMENT '关联二级类目ID',
  `name` VARCHAR(120) NOT NULL COMMENT '商品名称',
  `brand` VARCHAR(50) NOT NULL COMMENT '品牌',
  `cover_image` VARCHAR(255) DEFAULT '' COMMENT '商品主图',
  `description` TEXT COMMENT '商品详细描述与卖点 (供Agent检索)',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 0-下架, 1-上架',
  PRIMARY KEY (`id`),
  KEY `idx_category_id` (`category_id`),
  KEY `idx_brand` (`brand`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品SPU表';

-- 3. 商品 SKU 表
DROP TABLE IF EXISTS `skus`;
CREATE TABLE `skus` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'SKU ID',
  `product_id` BIGINT UNSIGNED NOT NULL COMMENT '关联SPU ID',
  `sku_code` VARCHAR(64) NOT NULL COMMENT 'SKU唯一编码',
  `spec_name` VARCHAR(100) NOT NULL COMMENT '规格描述 (如: 黑色 / 256GB)',
  `price` DECIMAL(10,2) NOT NULL COMMENT '售价',
  `stock` INT NOT NULL DEFAULT 0 COMMENT '库存',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 0-停售, 1-在售',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sku_code` (`sku_code`),
  KEY `idx_product_id` (`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品SKU表';

SET FOREIGN_KEY_CHECKS = 1;


-- ============================================================
-- 二、 插入 10 个类目 (4个一级大类 + 6个二级细分小类)
-- ============================================================
INSERT INTO `categories` (`id`, `name`, `parent_id`, `sort_order`) VALUES
(1, '数码电器', NULL, 1),
(2, '服饰箱包', NULL, 2),
(3, '户外运动', NULL, 3),
(4, '家居生活', NULL, 4),
(5, '智能手机', 1, 1),
(6, '音频设备', 1, 2),
(7, '男装外套', 2, 1),
(8, '运动鞋靴', 2, 2),
(9, '露营装备', 3, 1),
(10, '智能家电', 4, 1);


-- ============================================================
-- 三、 插入 50 个商品 SPU (分别挂载在 5~10 的二级类目下)
-- ============================================================

-- 类目 5: 智能手机 (共 8 个)
INSERT INTO `products` (`id`, `category_id`, `name`, `brand`, `description`) VALUES
(1, 5, 'iPhone 15 Pro Max', 'Apple', '搭载 A17 Pro 芯片，钛金属设计，5倍光学变焦。'),
(2, 5, '华为 Mate 60 Pro', '华为', '卫星通话，玄武架构超可靠，鸿蒙OS系统。'),
(3, 5, '小米 14 Ultra', '小米', '徕卡全明星四摄，一英寸主摄，专业影像旗舰。'),
(4, 5, 'vivo X100 Pro', 'vivo', '天玑9300芯片，蔡司APO超级长焦，续航持久。'),
(5, 5, 'OPPO Find X7 Ultra', 'OPPO', '双潜望长焦，哈苏专业影像，巅峰性能。'),
(6, 5, '三星 Galaxy S24 Ultra', '三星', '内置 S Pen，AI 实时翻译，第三代骁龙8for Galaxy。'),
(7, 5, '荣耀 Magic6 Pro', '荣耀', '巨犀玻璃，荣耀鸿燕通信，单反级鹰眼相机。'),
(8, 5, '一加 12', '一加', '超越 Pro 的性能，东方屏，哈苏影像加持。');

-- 类目 6: 音频设备 (共 8 个)
INSERT INTO `products` (`id`, `category_id`, `name`, `brand`, `description`) VALUES
(9, 6, '索尼 WH-1000XM5 降噪耳机', '索尼', '行业领先主动降噪，30小时超长续航，佩戴舒适。'),
(10, 6, 'Bose QuietComfort Ultra', 'Bose', '沉浸式音频，世界级消噪技术，至臻音质。'),
(11, 6, 'AirPods Pro 2', 'Apple', 'H2 芯片驱动，主动降噪性能翻倍，个性化空间音频。'),
(12, 6, 'JBS Pulse 4 蓝牙音箱', 'JBL', '360度炫彩 LED 灯效，震撼低音，防水便携。'),
(13, 6, 'Marshall Stanmore III', '马歇尔', '摇滚经典复古设计，宽广声场，蓝牙5.2。'),
(14, 6, '森海塞尔 Momentum 4', '森海塞尔', '发烧级音质，智能触控，60小时持久续航。'),
(15, 6, '漫步者 S1000W', '漫步者', 'Hi-Res 高清认证，多模连接，木质箱体低音炮。'),
(16, 6, 'B&W Px7 S2', '宝华韦健', '定制驱动单元，高解析度无线降噪耳机。');

-- 类目 7: 男装外套 (共 8 个)
INSERT INTO `products` (`id`, `category_id`, `name`, `brand`, `description`) VALUES
(17, 7, '北面 冲锋衣三合一', 'The North Face', '防水防风透气面料，可拆卸内胆，户外出行必备。'),
(18, 7, '始祖鸟 Beta LT 冲锋衣', 'Arc\'teryx', 'GORE-TEX 顶级面料，轻量化硬壳防水夹克。'),
(19, 7, '波司登 极寒系列羽绒服', '波司登', '90% 高蓬松鹅绒，蓄热锁温，严冬保暖。'),
(20, 7, '迪卡侬 抓绒衣男士保暖外套', 'Decathlon', '轻便透气，亲肤舒适，春秋户外徒步休闲。'),
(21, 7, '哥伦比亚 三合一防水外套', 'Columbia', 'Omni-Heat 自发热科技，全天候应对恶劣天气。'),
(22, 7, '耐克 NSW 休闲夹克', 'Nike', '经典街头风设计，防风舒适，日常百搭。'),
(23, 7, '阿迪达斯 经典三条纹运动外套', 'Adidas', '复古运动剪裁，透气面料，吸汗速干。'),
(24, 7, '优衣库 登山夹克', 'Uniqlo', '简约剪裁，轻度防水，日常通勤必备。');

-- 类目 8: 运动鞋靴 (共 8 个)
INSERT INTO `products` (`id`, `category_id`, `name`, `brand`, `description`) VALUES
(25, 8, '耐克 Air Zoom Pegasus 40', 'Nike', '回弹缓震，透气鞋面，专业公路跑步鞋。'),
(26, 8, '阿迪达斯 UltraBoost Light', 'Adidas', '轻量化 BOOST 中底，终极能量反馈。'),
(27, 8, 'HOKA ONE ONE Clifton 9', 'HOKA', '超厚缓震中底，长距离跑步无压力，轻量舒适。'),
(28, 8, '萨洛蒙 XT-6 越野跑鞋', 'Salomon', '经典全地形越野鞋，Quicklace 快速系带系统。'),
(29, 8, '亚瑟士 GEL-KAYANO 30', 'Asics', '顶级支撑稳定跑鞋，护膝保护，适合大体重。'),
(30, 8, '新百伦 990v6 复古跑鞋', 'New Balance', '总统慢跑鞋，猪皮拼接网眼，复古潮流。'),
(31, 8, '安踏 炽热专业篮球鞋', '安踏', '缓震耐磨，实战利器，透气包裹。'),
(32, 8, '特步 氢风科技跑步鞋', '特步', '超轻透气，夏季清爽不闷脚。');

-- 类目 9: 露营装备 (共 9 个)
INSERT INTO `products` (`id`, `category_id`, `name`, `brand`, `description`) VALUES
(33, 9, '牧高笛 自由之星2 户外帐篷', '牧高笛', '防暴雨级210T面料，自立式双十字支架。'),
(34, 9, '挪客 云尚超轻双人帐篷', 'Naturehike', '20D硅布超轻防雨，登山徒步轻量化首选。'),
(35, 9, '黑鹿 铝合金折叠蛋巢桌椅组合', 'BlackDeer', '便携式露营桌椅，组装简便，坚固耐用。'),
(36, 9, 'Alpine Peak 户外车载冰箱', 'Alpine', '强力压缩机速冻，露营自驾冷饮必备。'),
(37, 9, '火枫 星火便携式防风炉头', 'Fire-Maple', '大功率聚能燃烧，高海拔抗风露营炉具。'),
(38, 9, 'Snow Peak 钛金双层马克杯', 'Snow Peak', '超轻钛金属材质，折叠手柄，露营泡茶神器。'),
(39, 9, '科勒曼 营地车载推车', 'Coleman', '大容量折叠手推车，越野大轮，轻松拉货。'),
(40, 9, '骆驼 充气床垫双人加厚', 'Camel', '自动充气防潮垫，露营帐篷内铺设，睡眠舒适。'),
(41, 9, '伯希和 户外防水大天幕', 'Pelliot', '黑胶防晒涂层，遮阳隔热，搭建面积大。');

-- 类目 10: 智能家电 (共 9 个)
INSERT INTO `products` (`id`, `category_id`, `name`, `brand`, `description`) VALUES
(42, 10, '戴森 V12 Detect Slim 无绳吸尘器', 'Dyson', '激光探测微尘，轻量化设计，强劲数码马达。'),
(43, 10, '石头 G20 智能扫拖机器人', 'Roborock', '双螺旋自清洁扫拖，AI 避障，自动集尘上下水。'),
(44, 10, '科沃斯 T20 PRO 扫拖一体机', 'ECOVACS', '55度热水洗拖布，自动回洗，边角深度清洁。'),
(45, 10, '添可 芙万 3.0 智能洗地机', 'Tineco', '双贴边无死角，智能自清洁，洗拖烘一体。'),
(46, 10, '小米 智能空气净化器 4 Pro', '小米', '高效除醛除菌，OLED 触控屏，低噪运行。'),
(47, 10, '美的 变频冷暖空调 1.5匹', '美的', '新一级能效，ECO 节能模式，静音省电。'),
(48, 10, '九阳 智能太空无油空气炸锅', 'Joyoung', '可视大容量，智能温控，健康低脂少油。'),
(49, 10, '摩飞 便携式无线榨汁机', 'Morphy Richards', '双杯随行，强劲动力，随时随地鲜榨果汁。'),
(50, 10, '追觅 H20 Ultra 智能洗地机', 'Dreame', '热风烘干，恒压活水洗地，毛发防缠绕。');


-- ============================================================
-- 四、 为部分商品批量生成测试 SKU 规格与库存
-- ============================================================
-- ============================================================
-- 50个商品专属高清手写级 SKU 规格与库存数据
-- ============================================================

INSERT INTO `skus` (`product_id`, `sku_code`, `spec_name`, `price`, `stock`, `status`) VALUES
-- 1. iPhone 15 Pro Max
(1, 'SKU-IP15PM-BLK-128', '白色钛金属 / 128GB', 6999.00, 15, 1),
(1, 'SKU-IP15PM-BLK-256', '黑色钛金属 / 256GB', 9999.00, 15, 1),
(1, 'SKU-IP15PM-NAT-512', '原色钛金属 / 512GB', 11999.00, 8, 1),

-- 2. 华为 Mate 60 Pro
(2, 'SKU-M60P-GRN-512', '雅川青 / 512GB', 6999.00, 20, 1),
(2, 'SKU-M60P-BLK-512', '雅丹黑 / 512GB', 6999.00, 12, 1),

-- 3. 小米 14 Ultra
(3, 'SKU-XM14U-BLK-16G', '黑色素皮 / 16GB+512GB', 6499.00, 25, 1),
(3, 'SKU-XM14U-WHT-1T', '钛合白 / 16GB+1TB', 6999.00, 10, 1),

-- 4. vivo X100 Pro
(4, 'SKU-VIVOX100-BLU', '星迹蓝 / 16GB+512GB', 4999.00, 18, 1),
(4, 'SKU-VIVOX100-ORG', '落日橙 / 16GB+1TB', 5499.00, 7, 1),

-- 5. OPPO Find X7 Ultra
(5, 'SKU-OPPOX7-BLU', '海阔天空 / 16GB+256GB', 5999.00, 14, 1),
(5, 'SKU-OPPOX7-BRN', '大漠银月 / 16GB+512GB', 6499.00, 9, 1),

-- 6. 三星 Galaxy S24 Ultra
(6, 'SKU-S24U-GRY-256', '钛灰 / 12GB+256GB', 9699.00, 6, 1),
(6, 'SKU-S24U-BLK-512', '钛黑 / 12GB+512GB', 10699.00, 4, 1),

-- 7. 荣耀 Magic6 Pro
(7, 'SKU-HONOR6P-WHT', '祁连雪 / 16GB+512GB', 5699.00, 15, 1),
(7, 'SKU-HONOR6P-GRN', '海湖青 / 16GB+1TB', 6199.00, 8, 1),

-- 8. 一加 12
(8, 'SKU-ONEPLUS12-GRN', '苍绿 / 16GB+512GB', 4299.00, 30, 1),
(8, 'SKU-ONEPLUS12-BLK', '岩黑 / 16GB+256GB', 3799.00, 22, 1),

-- 9. 索尼 WH-1000XM5 降噪耳机
(9, 'SKU-XM5-BLK', '黑色 / 标准版', 2299.00, 35, 1),
(9, 'SKU-XM5-SLV', '银色 / 标准版', 2299.00, 18, 1),

-- 10. Bose QuietComfort Ultra
(10, 'SKU-BOSE-QC-BLK', '黑色 / 沉浸消噪版', 2499.00, 20, 1),
(10, 'SKU-BOSE-QC-WHT', '白色 / 沉浸消噪版', 2499.00, 11, 1),

-- 11. AirPods Pro 2
(11, 'SKU-APP-PRO2-WHT', '白色 / USB-C接口', 1899.00, 50, 1),

-- 12. JBL Pulse 4 蓝牙音箱
(12, 'SKU-JBL-PULSE4-BLK', '黑色 / 360度炫彩灯效', 1399.00, 16, 1),

-- 13. Marshall Stanmore III
(13, 'SKU-MARSH-ST3-BLK', '经典黑 / 复古摇滚版', 2999.00, 8, 1),

-- 14. 森海塞尔 Momentum 4
(14, 'SKU-SENN-M4-BLK', '黑色 / 发烧无线版', 2699.00, 12, 1),

-- 15. 漫步者 S1000W
(15, 'SKU-EDIF-S1000W', '木纹棕 / Hi-Res双声道', 1098.00, 20, 1),

-- 16. B&W Px7 S2
(16, 'SKU-BW-PX7S2-BLK', '碳黑色 / 旗舰降噪', 3299.00, 5, 1),

-- 17. 北面 冲锋衣三合一
(17, 'SKU-TNF-3IN1-BLK-L', '经典黑 / L码', 1499.00, 25, 1),
(17, 'SKU-TNF-3IN1-GRN-XL', '军绿色 / XL码', 1499.00, 18, 1),

-- 18. 始祖鸟 Beta LT 冲锋衣
(18, 'SKU-ARC-BLU-M', '蓝色 / M码', 4500.00, 5, 1),
(18, 'SKU-ARC-BLK-L', '黑色 / L码', 4500.00, 3, 1),

-- 19. 波司登 极寒系列羽绒服
(19, 'SKU-BSD-COLD-BLK', '极光黑 / 185(XXL)', 2199.00, 14, 1),
(19, 'SKU-BSD-COLD-WHT', '珍珠白 / 175(XL)', 2199.00, 10, 1),

-- 20. 迪卡侬 抓绒衣男士保暖外套
(20, 'SKU-DEC-FLEECE-GRY', '深灰色 / L码', 149.00, 60, 1),

-- 21. 哥伦比亚 三合一防水外套
(21, 'SKU-COL-3IN1-BLU', '深蓝色 / L码', 1299.00, 15, 1),

-- 22. 耐克 NSW 休闲夹克
(22, 'SKU-NIKE-NSW-BLK', '黑色 / L码', 699.00, 30, 1),

-- 23. 阿迪达斯 经典三条纹运动外套
(23, 'SKU-ADID-STR-BLK', '黑白三条纹 / L码', 499.00, 40, 1),

-- 24. 优衣库 登山夹克
(24, 'SKU-UNI-MOUN-KHA', '卡其色 / L码', 399.00, 50, 1),

-- 25. 耐克 Air Zoom Pegasus 40
(25, 'SKU-NIKE-PEG40-42', '黑白配色 / 42.5码', 899.00, 35, 1),
(25, 'SKU-NIKE-PEG40-41', '灰蓝配色 / 41码', 899.00, 22, 1),

-- 26. 阿迪达斯 UltraBoost Light
(26, 'SKU-ADID-UB-BLK', '全黑配色 / 42码', 1399.00, 18, 1),

-- 27. HOKA ONE ONE Clifton 9
(27, 'SKU-HOKA-C9-OAT', '燕麦色 / 41.5码', 1199.00, 12, 1),

-- 28. 萨洛蒙 XT-6 越野跑鞋
(28, 'SKU-SAL-XT6-BLK', '经典黑灰 / 42码', 1298.00, 15, 1),

-- 29. 亚瑟士 GEL-KAYANO 30
(29, 'SKU-ASICS-K30-GRY', '黑银配色 / 42.5码', 1390.00, 20, 1),

-- 30. 新百伦 990v6 复古跑鞋
(30, 'SKU-NB-990V6-GRY', '元祖灰 / 42码', 1899.00, 10, 1),

-- 31. 安踏 炽热专业篮球鞋
(31, 'SKU-ANTA-BASK-RED', '黑红实战配色 / 43码', 599.00, 45, 1),

-- 32. 特步 氢风科技跑步鞋
(32, 'SKU-XTEP-HYD-WHT', '清爽白 / 42码', 299.00, 80, 1),

-- 33. 牧高笛 自由之星2 户外帐篷
(33, 'SKU-MGD-GRN', '橄榄绿 / 标准款', 459.00, 50, 1),

-- 34. 挪客 云尚超轻双人帐篷
(34, 'SKU-NH-TENT-GRY', '灰色 / 20D超轻防雨版', 399.00, 30, 1),

-- 35. 黑鹿 铝合金折叠蛋巢桌椅组合
(35, 'SKU-BD-CHAIR-BLK', '黑色折叠桌椅套装', 488.00, 25, 1),

-- 36. Alpine Peak 户外车载冰箱
(36, 'SKU-ALP-FRIDGE-30L', '30L车载压缩机速冻版', 1580.00, 8, 1),

-- 37. 火枫 星火便携式防风炉头
(37, 'SKU-FM-STOVE-STD', '标准便携防风款', 198.00, 40, 1),

-- 38. Snow Peak 钛金双层马克杯
(38, 'SKU-SP-CUP-450', '450ml钛双层折叠柄', 248.00, 60, 1),

-- 39. 科勒曼 营地车载推车
(39, 'SKU-COL-CART-BLU', '大轮越野营地车 / 蓝色', 699.00, 12, 1),

-- 40. 骆驼 充气床垫双人加厚
(40, 'SKU-CAML-PAD-THK', '双人加厚自动充气垫', 269.00, 35, 1),

-- 41. 伯希和 户外防水大天幕
(41, 'SKU-PELL-CANOPY-BLK', '黑胶防晒涂层 / 大号', 359.00, 22, 1),

-- 42. 戴森 V12 Detect Slim 无绳吸尘器
(42, 'SKU-DYS-V12-YLW', '黄色 / 激光探测版', 4999.00, 10, 1),

-- 43. 石头 G20 智能扫拖机器人
(43, 'SKU-ROBO-G20-SIL', '星河银 / 智能上下水版', 4999.00, 12, 1),

-- 44. 科沃斯 T20 PRO 扫拖一体机
(44, 'SKU-ECO-T20-WHT', '白色 / 55度热水洗布版', 3999.00, 15, 1),

-- 45. 添可 芙万 3.0 智能洗地机
(45, 'SKU-TIN-V3-SLV', '太空银 / 双贴边无死角', 2990.00, 20, 1),

-- 46. 小米 智能空气净化器 4 Pro
(46, 'SKU-MI-AIR4P-WHT', '白色 / 高效除醛除菌版', 1299.00, 40, 1),

-- 47. 美的 变频冷暖空调 1.5匹
(47, 'SKU-MIDEA-AC-1.5', '1.5匹 / 新一级能效', 2399.00, 18, 1),

-- 48. 九阳 智能太空无油空气炸锅
(48, 'SKU-JOY-FRYER-5.5', '5.5L 可视大容量', 399.00, 50, 1),

-- 49. 摩飞 便携式无线榨汁机
(49, 'SKU-MORPH-JUICE-GRN', '复古绿 / 无线便携随行', 218.00, 65, 1),

-- 50. 追觅 H20 Ultra 智能洗地机
(50, 'SKU-DREAM-H20U', '热风烘干 / 旗舰款', 3699.00, 14, 1);